"""角色定义的解析与校验：名字、kind、读写模式、要传给 CLI 的参数。

和 run 的存储分开：这里只管"角色长什么样"，不碰磁盘。
"""

import re
import shlex

from . import config
from .errors import RunError


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
        "cli_args": [],
        "pane_id": None,
        "tab_id": None,
        "workspace_id": None,
        "worktree": None,
        "dispatched_at": None,
        "finished_at": None,
        "error": None,
    }


def split_cli_args(value):
    """按 shell 规则切分参数串，但**不把反斜杠当转义符**。

    默认的 shlex.split 是 POSIX 模式，会把 `C:\\Users\\x` 吃成 `C:Usersx`，
    Windows 路径直接废掉。这里保留引号语义、关掉转义。
    """
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)


def apply_role_args(roles, specs):
    """把 `角色名=--model xxx --effort high` 挂到对应角色上。

    参数原样跟在自主档参数后面传给该 agent 自己的 CLI。
    模型怎么选是编排器读 modelselect.md 之后的决定，脚本不猜。
    """
    if not specs:
        return
    index = {role["name"]: role for role in roles}
    for spec in specs:
        name, sep, value = spec.partition("=")
        name = name.strip()
        if not sep:
            raise RunError("--role-args 要写成 角色名=参数，收到 {!r}".format(spec))
        if name not in index:
            raise RunError(
                "--role-args 指向了不存在的角色 {}；已定义的是 {}".format(
                    name, ", ".join(index) or "无"
                )
            )
        index[name]["cli_args"] = split_cli_args(value)


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


def validate(roles, isolation):
    """建 run 之前的整体校验，返回可写角色名列表。"""
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
