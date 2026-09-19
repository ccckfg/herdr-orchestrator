"""并发等待：一次 api snapshot 拿到所有 agent 状态，配合结果文件落盘判完成。

判定原则（写进设计的硬规则）：
  完成 = 结果文件落盘且大小稳定。不拿 agent 状态当完成信号——
  herdr 的 idle / done 只表示"能接受输入"，unknown 更不代表干完了。
  agent 状态只用来判断：还活着吗、是不是卡在审批框、有没有真的动过。
"""

import os
import time

from . import config, herdr, runstore


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _capture_dialog(manifest, role):
    """把弹窗画面抓进日志文件，供编排器或用户判断该怎么回应。"""
    try:
        text = herdr.pane_read(role["pane_id"], lines=config.BLOCKED_CAPTURE_LINES)
    except herdr.HerdrError as exc:
        return "抓屏失败：{}".format(exc)
    path = runstore.log_path(manifest, role["name"])
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError:
        pass
    return text.strip()


def _finish(manifest, role, state, error=None):
    role["state"] = state
    role["error"] = error
    role["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    runstore.save(manifest)


def watch(manifest, role_names=None, timeout_s=None, interval_s=None, on_event=None):
    """轮询直到所有目标角色落定或整轮超时。返回 [(角色, 终态, 说明)]。"""
    timeout_s = timeout_s or config.DEFAULT_WATCH_TIMEOUT_S
    interval_s = interval_s or config.DEFAULT_POLL_INTERVAL_S
    notify = on_event or (lambda *_: None)

    pending = [
        role
        for role in runstore.roles_by_names(manifest, role_names)
        if role["state"] == config.STATE_DISPATCHED
    ]
    settled = [
        (role["name"], role["state"], role.get("error") or "")
        for role in runstore.roles_by_names(manifest, role_names)
        if role["state"] in config.TERMINAL_STATES
    ]
    if not pending:
        return settled

    sizes = {}
    deadline = time.time() + timeout_s

    while pending and time.time() < deadline:
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError as exc:
            notify("snapshot", None, "快照读取失败，继续重试：{}".format(exc))
            time.sleep(interval_s)
            continue

        for role in list(pending):
            name = role["name"]
            agent = herdr.find_agent(snap, pane_id=role.get("pane_id"), name=name)
            status = (agent or {}).get("agent_status")
            if status == config.AGENT_WORKING:
                role["observed_working"] = True

            # 1) 卡在审批/提问界面
            if status == config.AGENT_BLOCKED:
                dialog = _capture_dialog(manifest, role)
                if manifest.get("on_blocked") == config.ON_BLOCKED_DECIDE:
                    # 自动档：抓屏交给编排器自己判断，再用 answer 回应后重新 watch
                    hint = "弹窗已抓到 {}，读完用 answer 回应".format(
                        runstore.log_path(manifest, name)
                    )
                else:
                    hint = "需要人工处理"
                _finish(manifest, role, config.STATE_BLOCKED, "卡在审批/提问界面：" + hint)
                pending.remove(role)
                settled.append((name, config.STATE_BLOCKED, dialog or hint))
                notify("blocked", name, hint)
                continue

            out = runstore.out_path(manifest, name)
            size = _file_size(out)

            # 2) agent 不见了（窗格被关 / 进程退出）
            if agent is None:
                if size:
                    _finish(manifest, role, config.STATE_DONE)
                    pending.remove(role)
                    settled.append((name, config.STATE_DONE, out))
                    notify("done", name, out)
                else:
                    _finish(manifest, role, config.STATE_FAILED, "agent 已消失且没有结果文件")
                    pending.remove(role)
                    settled.append((name, config.STATE_FAILED, "agent 消失"))
                    notify("failed", name, "agent 消失")
                continue

            # 3) 结果文件落盘且连续 N 次大小不变 = 写完了
            if size:
                previous, stable = sizes.get(name, (None, 0))
                stable = stable + 1 if previous == size else 0
                sizes[name] = (size, stable)
                if stable >= config.STABLE_POLLS - 1:
                    _finish(manifest, role, config.STATE_DONE)
                    pending.remove(role)
                    settled.append((name, config.STATE_DONE, out))
                    notify("done", name, out)
                    continue
            notify("poll", name, status or "unknown")

        if pending:
            time.sleep(interval_s)

    for role in pending:
        hint = "整轮超时"
        if not role.get("observed_working"):
            hint += "；全程没观察到 working，提示可能压根没投递进去，用 peek 看屏幕再决定"
        _finish(manifest, role, config.STATE_TIMEOUT, hint)
        settled.append((role["name"], config.STATE_TIMEOUT, hint))
        notify("timeout", role["name"], hint)

    states = [role["state"] for role in manifest["roles"]]
    if all(state == config.STATE_DONE for state in states):
        manifest["state"] = config.STATE_DONE
    elif any(state == config.STATE_BLOCKED for state in states):
        manifest["state"] = config.STATE_BLOCKED
    runstore.save(manifest)
    return settled
