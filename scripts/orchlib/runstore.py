"""run 目录与 manifest 的读写。

一次编排 = 一个 run 目录，所有任务卡、结果卡、日志、清理清单都在里面。
"""

import json
import os
import secrets
import time

from . import config, roles as rolelib
from .errors import RunError  # noqa: F401  上层按 runstore.RunError 捕获


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


def modelselect_candidates(cwd):
    """模型偏好文档的查找顺序：项目级优先，其次用户级。"""
    return [
        os.path.normpath(os.path.join(orch_root(cwd), config.MODELSELECT_FILENAME)),
        os.path.normpath(
            os.path.join(
                os.path.expanduser(config.USER_ORCH_DIR), config.MODELSELECT_FILENAME
            )
        ),
    ]


def find_modelselect(cwd):
    """定位模型偏好文档，找不到返回 None。"""
    for path in modelselect_candidates(cwd):
        if os.path.isfile(path):
            return path
    return None


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


# ------------------------------------------------------------------ manifest

def create_run(cwd, roles, isolation, task_text, context, autonomy=None):
    if isolation not in config.ISOLATION_MODES:
        raise RunError("未知隔离模式 {}；可选 {}".format(isolation, config.ISOLATION_MODES))
    autonomy = autonomy or config.DEFAULT_AUTONOMY
    if autonomy not in config.AUTONOMY_LEVELS:
        raise RunError("未知自主档位 {}；可选 {}".format(autonomy, config.AUTONOMY_LEVELS))
    rolelib.validate(roles, isolation)

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
