"""汇总各角色的结果卡，产出 summary.md。

主控只需要读这一个文件，不必逐个翻 out/。
"""

import os

from . import config, runstore

_NEEDS_HUMAN = (config.STATE_BLOCKED, config.STATE_FAILED, config.STATE_TIMEOUT)


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().strip()


def _table(manifest):
    lines = [
        "| 角色 | kind | 读写 | 状态 | 结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for role in manifest["roles"]:
        out = runstore.out_path(manifest, role["name"])
        mark = "有" if os.path.isfile(out) else "无"
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                role["name"],
                role.get("kind") or "-",
                role["mode"],
                role["state"],
                mark,
            )
        )
    return "\n".join(lines)


def build(manifest):
    task = _read(os.path.join(manifest["run_dir"], config.TASK_FILE_NAME)) or "(未填写)"
    parts = [
        "# 编排汇总 {}".format(manifest["run_id"]),
        "",
        "- 工作目录：`{}`".format(manifest["cwd"]),
        "- 隔离模式：{}".format(manifest["isolation"]),
        "- 创建时间：{}".format(manifest["created_at"]),
        "",
        "## 原始任务",
        "",
        task,
        "",
        "## 角色一览",
        "",
        _table(manifest),
        "",
    ]

    attention = [role for role in manifest["roles"] if role["state"] in _NEEDS_HUMAN]
    if attention:
        parts += ["## 需要人工处理", ""]
        for role in attention:
            parts.append(
                "- **{}**（{}）：{}".format(
                    role["name"], role["state"], role.get("error") or "无说明"
                )
            )
        parts.append("")

    for role in manifest["roles"]:
        name = role["name"]
        body = _read(runstore.out_path(manifest, name))
        parts += ["## {} 的结果".format(name), ""]
        if body:
            parts += [body, ""]
        else:
            parts += [
                "> 没有结果文件。状态 {}，说明：{}".format(
                    role["state"], role.get("error") or "无"
                ),
                "",
            ]

    text = "\n".join(parts).rstrip() + "\n"
    path = runstore.summary_path(manifest)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path, text
