"""起 agent 与投递任务卡。

投递一律不带 --wait：--wait 是阻塞的，一次只能等一个 agent，真并行必须
"先全部投递、再统一轮询"，等待交给 watch 模块。
"""

import os
import time

from . import config, herdr, layout, runstore


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _role_env(manifest, role_name):
    return {
        config.ENV_RUN_DIR: manifest["run_dir"],
        config.ENV_ROLE: role_name,
        config.ENV_OUT: runstore.out_path(manifest, role_name),
    }


def spawn(manifest, role_names=None, trust=False):
    """为每个角色准备窗格并启动对应 kind 的 agent。"""
    targets = [
        role
        for role in runstore.roles_by_names(manifest, role_names)
        if role["state"] == config.STATE_PLANNED
    ]
    if not targets:
        return []

    available = herdr.available_kinds()
    worktree_mode = manifest["isolation"] == config.ISOLATION_WORKTREE
    plain = [
        role
        for role in targets
        if not (worktree_mode and role["mode"] == config.MODE_WRITE)
    ]
    allocator = layout.PaneAllocator(manifest, len(plain))

    results = []
    for role in targets:
        name = role["name"]
        try:
            kind = runstore.resolve_kind(role, available)
        except runstore.RunError as exc:
            role["state"] = config.STATE_FAILED
            role["error"] = str(exc)
            results.append((name, config.STATE_FAILED, str(exc)))
            continue

        try:
            if worktree_mode and role["mode"] == config.MODE_WRITE:
                slot = layout.allocate_worktree(manifest, name, trust=trust)
                role["worktree"] = slot.pop("worktree")
            else:
                slot = allocator.next_pane(manifest["cwd"], _role_env(manifest, name))
        except herdr.HerdrError as exc:
            role["state"] = config.STATE_FAILED
            role["error"] = "分配窗格失败：{}".format(exc)
            results.append((name, config.STATE_FAILED, role["error"]))
            runstore.save(manifest)
            continue

        autonomy = manifest.get("autonomy", config.DEFAULT_AUTONOMY)
        extra = runstore.autonomy_args(kind, autonomy)
        role["kind"] = kind
        role["pane_id"] = slot["pane_id"]
        role["tab_id"] = slot.get("tab_id")
        role["workspace_id"] = slot.get("workspace_id")
        role["autonomy_args"] = extra
        # 该 kind 没有绕过开关时必须说出来，否则会以为设了 yolo 就不会再弹窗
        role["autonomy_effective"] = bool(extra) or autonomy == config.AUTONOMY_ASK
        runstore.save(manifest)

        try:
            herdr.agent_start(name, kind, role["pane_id"], extra_args=extra)
        except herdr.HerdrError as exc:
            # agent_not_ready：进程起来了但卡在弹窗，名字仍然可用于读屏
            if exc.code == "agent_not_ready":
                role["state"] = config.STATE_BLOCKED
                role["error"] = "启动后卡在交互界面（{}），需要人工看一眼".format(exc.code)
            else:
                role["state"] = config.STATE_FAILED
                role["error"] = "启动失败：{}".format(exc)
            results.append((name, role["state"], role["error"]))
            runstore.save(manifest)
            continue

        role["state"] = config.STATE_SPAWNED
        role["error"] = None
        note = role["pane_id"]
        if not role["autonomy_effective"]:
            note += "  ! kind={} 没有 {} 档开关，它仍会弹自己的审批框".format(
                kind, autonomy
            )
        results.append((name, config.STATE_SPAWNED, note))
        runstore.save(manifest)

    manifest["state"] = config.STATE_SPAWNED
    runstore.save(manifest)
    return results


def _wait_ready(pane_id, timeout_s=None):
    """等到 agent 真的能吃输入。

    agent start 返回"就绪"时 TUI 可能还在画启动画面，这时投进去的文字会被吞掉
    ——实测 droid 就是这样丢掉了整张任务卡。
    """
    deadline = time.time() + (timeout_s or config.SPAWN_READY_TIMEOUT_S)
    while time.time() < deadline:
        try:
            info = herdr.agent_get(pane_id).get("agent", {})
        except herdr.HerdrError as exc:
            return False, str(exc)
        status = info.get("agent_status")
        if status == config.AGENT_BLOCKED:
            return False, "blocked"
        # interactive_ready 在旧版本可能没有这个字段，缺失时按可用处理
        if info.get("interactive_ready") is not False and status in config.AGENT_SETTLED:
            time.sleep(config.POST_READY_GRACE_S)
            return True, status
        time.sleep(config.READY_POLL_S)
    return False, "ready_timeout"


def _wait_activity(pane_id, out_file):
    """投递后确认对方真的动了。没动就说明这一投大概率没进去。"""
    deadline = time.time() + config.ACTIVITY_GRACE_S
    while time.time() < deadline:
        try:
            info = herdr.agent_get(pane_id).get("agent", {})
        except herdr.HerdrError:
            return False
        if info.get("agent_status") in (config.AGENT_WORKING, config.AGENT_BLOCKED):
            return True
        if os.path.isfile(out_file) and os.path.getsize(out_file):
            return True
        time.sleep(config.ACTIVITY_POLL_S)
    return False


def dispatch(manifest, role_names=None, force=False):
    """把任务卡投递给已就绪的 agent。提示词只有一句话，正文在卡里。"""
    allowed = (config.STATE_SPAWNED,) if not force else (
        config.STATE_SPAWNED,
        config.STATE_DISPATCHED,
        config.STATE_TIMEOUT,
        config.STATE_BLOCKED,
    )
    targets = [
        role
        for role in runstore.roles_by_names(manifest, role_names)
        if role["state"] in allowed
    ]
    results = []
    for role in targets:
        name = role["name"]
        card = runstore.card_path(manifest, name)
        if not os.path.isfile(card):
            role["error"] = "任务卡不存在，先写卡：orch.py card --role {}".format(name)
            results.append((name, "skipped", role["error"]))
            continue

        ready, detail = _wait_ready(role["pane_id"])
        if not ready:
            if detail == "blocked":
                role["state"] = config.STATE_BLOCKED
                role["error"] = "投递前就卡在审批/提问界面，需要人工处理"
            else:
                role["error"] = "等不到可交互状态（{}），没有投递；用 peek 看屏幕".format(detail)
            results.append((name, role["state"], role["error"]))
            runstore.save(manifest)
            continue

        text = config.DISPATCH_PROMPT_TEMPLATE.format(card_path=card)
        try:
            herdr.agent_prompt(role["pane_id"], text)
        except herdr.HerdrError as exc:
            if exc.code == "agent_blocked":
                role["state"] = config.STATE_BLOCKED
                role["error"] = "投递前就卡在审批/提问界面，需要人工处理"
            else:
                role["state"] = config.STATE_FAILED
                role["error"] = "投递失败：{}".format(exc)
            results.append((name, role["state"], role["error"]))
            runstore.save(manifest)
            continue

        role["state"] = config.STATE_DISPATCHED
        role["dispatched_at"] = _now()
        role["error"] = None
        # 官方警告：超时/停滞不等于没投递成功，所以这里只记录不自动重投
        observed = _wait_activity(role["pane_id"], runstore.out_path(manifest, name))
        role["observed_working"] = observed
        if not observed:
            role["error"] = "投递后 {} 秒内没观察到 working：先 peek 看屏幕，确认没进去再 --force 重投".format(
                config.ACTIVITY_GRACE_S
            )
        results.append((name, config.STATE_DISPATCHED, role["error"] or card))
        runstore.save(manifest)

    manifest["state"] = config.STATE_DISPATCHED
    runstore.save(manifest)
    return results


def answer(manifest, role_name, keys):
    """回应某个角色的交互界面。

    keys 是 herdr 的逻辑键，如 "2" / "enter" / "esc" / "ctrl+c"，按顺序发送。
    herdr 会先校验所有键再写入，不会发一半。

    **先读屏再决定按什么**：不同 agent 的弹窗选项顺序不一样，盲按会选错
    （codex 的钩子弹窗里 1 是"去审查"、2 才是"信任并继续"）。
    ask 档下这个动作应该由用户做，不是编排器。
    """
    role = runstore.role(manifest, role_name)
    if not role.get("pane_id"):
        raise runstore.RunError("角色 {} 还没有窗格".format(role_name))
    if not keys:
        raise runstore.RunError("没有给要发送的键")
    herdr.agent_send_keys(role["pane_id"], *keys)
    role["error"] = "已发送按键 {}".format(" ".join(keys))
    if role["state"] == config.STATE_BLOCKED:
        # 回退到被卡住之前的那一档：卡在首启弹窗的还没收到任务卡，
        # 直接标成 dispatched 会让后续 dispatch 跳过它
        role["state"] = (
            config.STATE_DISPATCHED
            if role.get("dispatched_at")
            else config.STATE_SPAWNED
        )
        role["finished_at"] = None
    runstore.save(manifest)
    return role["state"]


def peek(manifest, role_name, lines=None):
    """读回某个角色的屏幕内容，只用于诊断，不作为完成依据。"""
    role = runstore.role(manifest, role_name)
    if not role.get("pane_id"):
        raise runstore.RunError("角色 {} 还没有窗格".format(role_name))
    text = herdr.pane_read(role["pane_id"], lines=lines or config.DEFAULT_PEEK_LINES)
    path = runstore.log_path(manifest, role_name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return text, path
