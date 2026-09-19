"""herdr CLI 的薄封装：负责调用、JSON 解析和错误归类。

只有这个模块知道 herdr 的命令行长什么样；上层拿到的都是 dict。
"""

import json
import os
import shutil
import subprocess

from . import config


class HerdrError(Exception):
    """herdr CLI 返回的错误。code 取自服务端 JSON，取不到时为 None。"""

    def __init__(self, message, code=None, argv=None, raw=""):
        super().__init__(message)
        self.code = code
        self.argv = argv or []
        self.raw = raw

    def __str__(self):
        base = super().__str__()
        return "[{}] {}".format(self.code, base) if self.code else base


def binary():
    """herdr 可执行文件路径。优先用 herdr 注入的绝对路径。"""
    return os.environ.get(config.ENV_HERDR_BIN) or "herdr"


def inside_herdr():
    return os.environ.get(config.ENV_HERDR_ACTIVE) == "1"


def available_kinds():
    """本机 PATH 上真能起起来的 agent kind。"""
    found = []
    for kind, exe in sorted(config.KIND_EXECUTABLES.items()):
        if shutil.which(exe):
            found.append(kind)
    return found


def _extract_error(text):
    """从 stderr 里尽力抠出 (code, message)。"""
    text = (text or "").strip()
    if not text:
        return None, "herdr 未返回错误内容"
    try:
        payload = json.loads(text)
    except ValueError:
        return None, text.splitlines()[0]
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return err.get("code"), err.get("message") or text
    return None, text


def call_raw(args, timeout=None, machine=None):
    """执行一条 herdr 命令，返回 stdout 原文。

    pane read / agent read 这类命令返回的是屏幕文本而不是 JSON，必须走这里。
    """
    argv = [binary()]
    if machine:
        argv += ["--machine", machine]
    argv += list(args)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or config.CLI_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise HerdrError("herdr 调用超时", code="cli_timeout", argv=argv)
    except FileNotFoundError:
        raise HerdrError("找不到 herdr 可执行文件", code="cli_missing", argv=argv)

    if proc.returncode != 0:
        code, message = _extract_error(proc.stderr or proc.stdout)
        raise HerdrError(message, code=code, argv=argv, raw=proc.stderr)
    return proc.stdout or ""


def call(args, timeout=None, machine=None):
    """执行一条 herdr 命令并返回 result 字典。

    args: 不含可执行文件名的参数列表，例如 ["agent", "list"]。
    """
    out = call_raw(args, timeout=timeout, machine=machine).strip()
    if not out:
        return {}
    try:
        payload = json.loads(out)
    except ValueError:
        raise HerdrError(
            "herdr 返回的不是 JSON", code="cli_bad_json", argv=list(args), raw=out
        )
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"] or {}
    return payload if isinstance(payload, dict) else {}


# ------------------------------------------------------------------ 只读查询

def snapshot():
    """整个会话的实时快照。一次调用即可拿到所有 agent 状态。"""
    return call(["api", "snapshot"]).get("snapshot", {})


def agents():
    return snapshot().get("agents", [])


def agent_get(target):
    return call(["agent", "get", target])


def agent_read(target, lines=None, source="recent-unwrapped"):
    """返回屏幕文本原文（不是 JSON）。"""
    args = ["agent", "read", target, "--source", source]
    if lines:
        args += ["--lines", str(lines)]
    return call_raw(args)


def pane_read(pane_id, lines=None, source="recent-unwrapped"):
    """返回屏幕文本原文（不是 JSON）。"""
    args = ["pane", "read", pane_id, "--source", source]
    if lines:
        args += ["--lines", str(lines)]
    return call_raw(args)


def pane_layout(pane_id):
    return call(["pane", "layout", "--pane", pane_id])


def version():
    proc = subprocess.run(
        [binary(), "--version"], capture_output=True, text=True, errors="replace"
    )
    return (proc.stdout or proc.stderr or "").strip()


# ------------------------------------------------------------------ 布局写操作

def _env_args(env):
    args = []
    for key, value in (env or {}).items():
        args += ["--env", "{}={}".format(key, value)]
    return args


def pane_split(source_pane, direction, cwd=None, env=None, focus=False):
    args = ["pane", "split", "--pane", source_pane, "--direction", direction]
    if cwd:
        args += ["--cwd", cwd]
    args += _env_args(env)
    args.append("--focus" if focus else "--no-focus")
    return call(args).get("pane", {})


def tab_create(workspace_id, cwd=None, label=None, env=None, focus=False):
    args = ["tab", "create", "--workspace", workspace_id]
    if cwd:
        args += ["--cwd", cwd]
    if label:
        args += ["--label", label]
    args += _env_args(env)
    args.append("--focus" if focus else "--no-focus")
    result = call(args)
    return result.get("tab", {}), result.get("root_pane", {})


def worktree_create(cwd, branch=None, path=None, label=None, trust=False):
    args = ["worktree", "create", "--cwd", cwd, "--no-focus"]
    if branch:
        args += ["--branch", branch]
    if path:
        args += ["--path", path]
    if label:
        args += ["--label", label]
    if trust:
        args.append("--trust-repository")
    return call(args)


def pane_close(pane_id):
    return call(["pane", "close", pane_id])


def tab_close(tab_id):
    return call(["tab", "close", tab_id])


def workspace_close(workspace_id, group=False):
    args = ["workspace", "close", workspace_id]
    if group:
        args.append("--group")
    return call(args)


# ------------------------------------------------------------------ agent 操作

def agent_start(name, kind, pane_id, timeout_ms=None, extra_args=None):
    """启动 agent。extra_args 走 `--` 之后，原样交给该 agent 自己的 CLI。"""
    args = ["agent", "start", name, "--kind", kind, "--pane", pane_id]
    args += ["--timeout", str(timeout_ms or config.DEFAULT_SPAWN_TIMEOUT_MS)]
    if extra_args:
        args.append("--")
        args += list(extra_args)
    # agent start 自身会等到就绪，CLI 硬超时要留出余量
    budget = (timeout_ms or config.DEFAULT_SPAWN_TIMEOUT_MS) / 1000.0 + 30
    return call(args, timeout=budget)


def agent_prompt(target, text):
    """非阻塞投递：不带 --wait，提交完就返回，由 watch 负责等待。"""
    return call(["agent", "prompt", target, text])


def agent_send_keys(target, *keys):
    return call(["agent", "send-keys", target] + list(keys))


# 快照里存放 agent 名字的字段在不同版本下叫法可能不同，按顺序试
AGENT_NAME_KEYS = ("name", "agent_name", "label")


def find_agent(snapshot_data, pane_id=None, name=None):
    """在快照里定位 agent 记录。窗格 ID 是最可靠的锚点，名字作为补充。"""
    for item in snapshot_data.get("agents", []):
        if pane_id and item.get("pane_id") == pane_id:
            return item
    if not name:
        return None
    for item in snapshot_data.get("agents", []):
        for key in AGENT_NAME_KEYS:
            if item.get(key) == name:
                return item
    return None
