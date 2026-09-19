"""run 目录与 manifest 的读写。

一次编排 = 一个 run 目录，所有任务卡、结果卡、日志、清理清单都在里面。
"""

import json
import os
import re
import secrets
import time

from . import config


class RunError(Exception):
    pass


# ------------------------------------------------------------------ 路径

def orch_root(cwd):
    return os.path.join(os.path.abspath(cwd), config.ORCH_DIR_NAME)


def ensure_root(cwd):
    """建 .herdr-orch/ 并让它自我忽略，不去动项目自己的 .gitignore。"""
    root = orch_root(cwd)
    os.makedirs(root, exist_ok=True)
    ignore = os.path.join(root, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(config.GITIGNORE_BODY)
    return root


def run_dir(cwd, run_id):
    return os.path.join(orch_root(cwd), run_id)


def list_runs(cwd):
    root = orch_root(cwd)
    if not os.path.isdir(root):
        return []
    names = [
        name
        for name in os.listdir(root)
        if os.path.isfile(os.path.join(root, name, config.MANIFEST_NAME))
    ]
    return sorted(names)


def latest_run(cwd):
    runs = list_runs(cwd)
    if not runs:
        raise RunError("当前目录还没有任何 run：先执行 orch.py new")
    return runs[-1]


def new_run_id():
    stamp = time.strftime(config.RUN_ID_TIME_FORMAT)
    return "{}-{}".format(stamp, secrets.token_hex(2))


def card_path(manifest, role_name):
    return os.path.join(manifest["run_dir"], config.TASKS_DIR_NAME, role_name + ".md")


def out_path(manifest, role_name):
    return os.path.join(manifest["run_dir"], config.OUT_DIR_NAME, role_name + ".md")


def log_path(manifest, role_name):
    return os.path.join(manifest["run_dir"], config.LOGS_DIR_NAME, role_name + ".log")


def summary_path(manifest):
    return os.path.join(manifest["run_dir"], config.SUMMARY_NAME)


# ------------------------------------------------------------------ 角色定义

def parse_role_spec(spec):
    """把 "reviewer" / "reviewer:codex" / "reviewer:codex:write" 解析成角色定义。"""
    parts = spec.split(":")
    name = parts[0].strip()
    if not re.match(config.ROLE_NAME_PATTERN, name):
        raise RunError(
            "角色名 {!r} 不合法：herdr 要求 [a-z][a-z0-9_-]{{0,31}}".format(name)
        )
    known = config.ROLE_LIBRARY.get(name, {})
    kind = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    mode = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    return {
        "name": name,
        "kind": kind,
        "mode": mode or known.get("mode", config.MODE_READ),
        "preferred_kinds": list(known.get("kinds", ())),
        "state": config.STATE_PLANNED,
        "pane_id": None,
        "tab_id": None,
        "workspace_id": None,
        "worktree": None,
        "dispatched_at": None,
        "finished_at": None,
        "error": None,
    }


def resolve_kind(role, available):
    """给角色挑一个本机起得来的 kind。"""
    if role.get("kind"):
        if role["kind"] not in available:
            raise RunError(
                "角色 {} 指定的 kind={} 在本机不可用；可用：{}".format(
                    role["name"], role["kind"], ", ".join(available) or "无"
                )
            )
        return role["kind"]
    for candidate in role.get("preferred_kinds", []):
        if candidate in available:
            return candidate
    raise RunError(
        "角色 {} 找不到可用 kind（候选 {}，本机可用 {}）；用 role:kind 显式指定".format(
            role["name"],
            ", ".join(role.get("preferred_kinds", [])) or "无",
            ", ".join(available) or "无",
        )
    )


def autonomy_args(kind, autonomy):
    """某个 kind 在指定自主档位下要附加的原生参数。

    返回空列表有两种含义：ask 档（本来就不加），或这个 kind 没有对应开关——
    后者意味着它仍然会弹自己的审批框，调用方要把这件事说出来。
    """
    if autonomy == config.AUTONOMY_ASK:
        return []
    return list(config.KIND_AUTONOMY_ARGS.get(kind, {}).get(autonomy, []))


def validate_roles(roles, isolation):
    names = [role["name"] for role in roles]
    if len(set(names)) != len(names):
        raise RunError("角色名必须唯一：{}".format(", ".join(names)))
    if len(roles) > config.MAX_PARALLEL_ROLES:
        raise RunError(
            "一轮最多 {} 个子 agent，当前 {} 个；拆成多轮".format(
                config.MAX_PARALLEL_ROLES, len(roles)
            )
        )
    writers = [role["name"] for role in roles if role["mode"] == config.MODE_WRITE]
    if isolation == config.ISOLATION_SINGLE_WRITER and len(writers) > 1:
        raise RunError(
            "single-writer 模式只允许一个写入者，当前有 {}；"
            "改用 --isolation worktree，或把多余的角色降为 read-only".format(
                ", ".join(writers)
            )
        )
    return writers


# ------------------------------------------------------------------ manifest

def create_run(cwd, roles, isolation, task_text, context, autonomy=None):
    if isolation not in config.ISOLATION_MODES:
        raise RunError("未知隔离模式 {}；可选 {}".format(isolation, config.ISOLATION_MODES))
    autonomy = autonomy or config.DEFAULT_AUTONOMY
    if autonomy not in config.AUTONOMY_LEVELS:
        raise RunError("未知自主档位 {}；可选 {}".format(autonomy, config.AUTONOMY_LEVELS))
    validate_roles(roles, isolation)

    ensure_root(cwd)
    run_id = new_run_id()
    directory = run_dir(cwd, run_id)
    for sub in (config.TASKS_DIR_NAME, config.OUT_DIR_NAME, config.LOGS_DIR_NAME):
        os.makedirs(os.path.join(directory, sub), exist_ok=True)

    manifest = {
        "run_id": run_id,
        "run_dir": directory,
        "cwd": os.path.abspath(cwd),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "isolation": isolation,
        "autonomy": autonomy,
        "on_blocked": (
            config.ON_BLOCKED_ESCALATE
            if autonomy == config.AUTONOMY_ASK
            else config.ON_BLOCKED_DECIDE
        ),
        "owner_pane_id": context.get("pane_id"),
        "owner_tab_id": context.get("tab_id"),
        "owner_workspace_id": context.get("workspace_id"),
        "roles": roles,
        "created_panes": [],
        "created_tabs": [],
        "created_workspaces": [],
        "state": config.STATE_PLANNED,
    }
    with open(
        os.path.join(directory, config.TASK_FILE_NAME), "w", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(task_text or "")
    save(manifest)
    return manifest


def load(cwd, run_id=None):
    run_id = run_id or latest_run(cwd)
    path = os.path.join(run_dir(cwd, run_id), config.MANIFEST_NAME)
    if not os.path.isfile(path):
        raise RunError("找不到 run {}（{}）".format(run_id, path))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save(manifest):
    path = os.path.join(manifest["run_dir"], config.MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def role(manifest, name):
    for item in manifest["roles"]:
        if item["name"] == name:
            return item
    raise RunError("run {} 里没有角色 {}".format(manifest["run_id"], name))


def roles_by_names(manifest, names):
    if not names:
        return list(manifest["roles"])
    return [role(manifest, name) for name in names]


# ------------------------------------------------------------------ 任务卡

def write_card(manifest, role_name, body):
    """写任务卡，并强制附加交付协议——协议由脚本负责，不靠主控记得写。"""
    item = role(manifest, role_name)
    out = out_path(manifest, role_name)
    if item["mode"] == config.MODE_WRITE:
        if item.get("worktree"):
            scope = config.WRITE_SCOPE_WORKTREE.format(path=item["worktree"]["path"])
        else:
            scope = config.WRITE_SCOPE_FULL
    else:
        scope = config.WRITE_SCOPE_READ_ONLY

    footer = config.PROTOCOL_FOOTER.format(
        out_path=out, role=role_name, write_scope=scope
    )
    path = card_path(manifest, role_name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body.rstrip() + "\n")
        handle.write(footer)
    return path
