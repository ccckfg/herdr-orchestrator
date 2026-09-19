"""各子命令的实现与输出格式化。

orch.py 只负责把命令行参数映射到这里的函数。
"""

import json
import os
import shutil
import sys

from . import cleanup as cleanup_mod
from . import collect as collect_mod
from . import config, dispatch, herdr, roles as rolelib, runstore, watch

_ROW = "{:12} {:10} {}"


def _emit(args, payload, text):
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


def _read_source(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _require_herdr():
    if not herdr.inside_herdr():
        raise SystemExit(
            "不在 herdr 窗格里（{}≠1）。本工具只能由 herdr 管理的 agent 运行。".format(
                config.ENV_HERDR_ACTIVE
            )
        )


def _context():
    return {
        "pane_id": os.environ.get(config.ENV_HERDR_PANE),
        "tab_id": os.environ.get(config.ENV_HERDR_TAB),
        "workspace_id": os.environ.get(config.ENV_HERDR_WORKSPACE),
    }


def _load(args):
    return runstore.load(args.cwd, getattr(args, "run", None))


def _rows(results):
    return "\n".join(_ROW.format(name, state, info) for name, state, info in results)


# ------------------------------------------------------------------ 命令

def doctor(args):
    context = _context()
    kinds = herdr.available_kinds()
    binary = herdr.binary()
    found = bool(shutil.which(binary) or os.path.isfile(binary))
    checks = {
        "inside_herdr": herdr.inside_herdr(),
        "herdr_binary": binary if found else None,
        "herdr_version": herdr.version() if found else "",
        "python": sys.version.split()[0],
        "cwd": os.path.abspath(args.cwd),
        "context": context,
        "available_kinds": kinds,
        "git_repo": os.path.isdir(os.path.join(os.path.abspath(args.cwd), ".git")),
        "runs": runstore.list_runs(args.cwd),
        "modelselect": runstore.find_modelselect(args.cwd),
    }
    problems = []
    if not found:
        problems.append("找不到 herdr 可执行文件：{}".format(binary))
    if not checks["inside_herdr"]:
        problems.append("HERDR_ENV≠1：不在 herdr 窗格里，所有编排命令都会拒绝执行")
    if not context["pane_id"]:
        problems.append("拿不到 HERDR_PANE_ID：分割窗格会退回到 UI 焦点窗格，有风险")
    if not kinds:
        problems.append("PATH 上找不到任何可用 agent CLI")
    if not checks["git_repo"]:
        problems.append("当前目录不是 git 仓库：--isolation worktree 不可用")
    if not checks["modelselect"]:
        problems.append(
            "没有模型偏好文档 {}：派活前请用户用自然语言写一份，放在 {}".format(
                config.MODELSELECT_FILENAME,
                " 或 ".join(runstore.modelselect_candidates(args.cwd)),
            )
        )
    checks["problems"] = problems

    lines = [
        "herdr        : {}".format(checks["herdr_version"] or "未知"),
        "在 herdr 内   : {}".format("是" if checks["inside_herdr"] else "否"),
        "窗格上下文    : {}".format(context),
        "可用 kind     : {}".format(", ".join(kinds) or "无"),
        "git 仓库      : {}".format("是" if checks["git_repo"] else "否"),
        "模型偏好      : {}".format(checks["modelselect"] or "未找到"),
        "历史 run      : {}".format(len(checks["runs"])),
    ]
    if problems:
        lines += [""] + ["! " + item for item in problems]
    _emit(args, checks, "\n".join(lines))
    return 0


def new(args):
    _require_herdr()
    roles = [rolelib.parse_role_spec(spec) for spec in args.role]
    rolelib.apply_role_args(roles, args.role_args)
    task = _read_source(args.task) if args.task else ""
    autonomy = config.AUTONOMY_YOLO if args.yolo else args.autonomy
    manifest = runstore.create_run(
        args.cwd, roles, args.isolation, task, _context(), autonomy=autonomy
    )
    lines = [
        "run {} 已创建：{}".format(manifest["run_id"], manifest["run_dir"]),
        "角色：{}".format(
            ", ".join(
                "{}({})".format(role["name"], role["mode"]) for role in manifest["roles"]
            )
        ),
        "隔离={}  自主档={}  弹窗策略={}".format(
            manifest["isolation"], manifest["autonomy"], manifest["on_blocked"]
        ),
    ]
    if autonomy == config.AUTONOMY_YOLO:
        writers = [r["name"] for r in manifest["roles"] if r["mode"] == config.MODE_WRITE]
        if writers and manifest["isolation"] != config.ISOLATION_WORKTREE:
            lines.append(
                "! yolo + 可写角色（{}）直接在工作目录上跑，没有沙箱也没有 worktree 兜底".format(
                    ", ".join(writers)
                )
            )
    lines.append("下一步：给每个角色写任务卡 orch.py card --role <名字> --file <文件>")
    _emit(args, manifest, "\n".join(lines))
    return 0


def answer(args):
    _require_herdr()
    manifest = _load(args)
    state = dispatch.answer(manifest, args.role, args.keys)
    _emit(
        args,
        {"role": args.role, "keys": args.keys, "state": state},
        "已向 {} 发送 {}；状态 {}，继续 watch".format(
            args.role, " ".join(args.keys), state
        ),
    )
    return 0


def card(args):
    manifest = _load(args)
    path = runstore.write_card(manifest, args.role, _read_source(args.file))
    _emit(args, {"role": args.role, "card": path}, "任务卡已写入（含交付协议）：" + path)
    return 0


def spawn(args):
    _require_herdr()
    manifest = _load(args)
    results = dispatch.spawn(manifest, args.role, trust=args.trust_repository)
    _emit(args, results, _rows(results) or "没有待启动的角色")
    return 0


def dispatch_cards(args):
    _require_herdr()
    manifest = _load(args)
    results = dispatch.dispatch(manifest, args.role, force=args.force)
    _emit(args, results, _rows(results) or "没有可投递的角色")
    return 0


def watch_run(args):
    _require_herdr()
    manifest = _load(args)

    def on_event(kind, name, info):
        if args.json or kind == "poll":
            return
        print("[{}] {} {}".format(kind, name or "", info), flush=True)

    results = watch.watch(
        manifest,
        args.role,
        timeout_s=args.timeout,
        interval_s=args.interval,
        on_event=on_event,
    )
    _emit(args, results, _rows(results) or "没有在等待的角色")
    return 0 if all(state == config.STATE_DONE for _, state, _ in results) else 1


def status(args):
    manifest = _load(args)
    lines = [
        "run {}  隔离={}  自主档={}  状态={}".format(
            manifest["run_id"],
            manifest["isolation"],
            manifest.get("autonomy", config.DEFAULT_AUTONOMY),
            manifest["state"],
        ),
        "目录 {}".format(manifest["run_dir"]),
        "",
    ]
    for role in manifest["roles"]:
        lines.append(
            "{:12} {:10} {:10} pane={} {}".format(
                role["name"],
                role["state"],
                role.get("kind") or "-",
                role.get("pane_id") or "-",
                role.get("error") or "",
            )
        )
    _emit(args, manifest, "\n".join(lines))
    return 0


def peek(args):
    _require_herdr()
    manifest = _load(args)
    text, path = dispatch.peek(manifest, args.role, lines=args.lines)
    _emit(args, {"role": args.role, "log": path, "text": text}, text)
    return 0


def collect(args):
    manifest = _load(args)
    path, text = collect_mod.build(manifest)
    _emit(args, {"summary": path}, text if args.print_summary else "汇总已写入：" + path)
    return 0


def cleanup(args):
    _require_herdr()
    manifest = _load(args)
    actions = cleanup_mod.cleanup(
        manifest, keep_panes=args.keep_panes, remove_worktrees=args.remove_worktrees
    )
    _emit(args, actions, _rows(actions) or "没有需要清理的资源")
    return 0
