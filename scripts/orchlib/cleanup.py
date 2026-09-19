"""清理本次编排创建的资源——而且只清理这些。

manifest 里的 created_* 是唯一依据：没登记过的窗格、tab、workspace 一律不动。
worktree 默认只关窗口、保留磁盘上的分支与改动，删除必须显式要求。
"""

from . import config, herdr, runstore


def cleanup(manifest, keep_panes=False, remove_worktrees=False):
    actions = []
    owner = manifest.get("owner_pane_id")

    if not keep_panes:
        for pane_id in list(manifest.get("created_panes", [])):
            if pane_id == owner:
                actions.append(("skip-pane", pane_id, "这是主控自己的窗格"))
                continue
            try:
                herdr.pane_close(pane_id)
                manifest["created_panes"].remove(pane_id)
                actions.append(("closed-pane", pane_id, ""))
            except herdr.HerdrError as exc:
                actions.append(("keep-pane", pane_id, str(exc)))

        for tab_id in list(manifest.get("created_tabs", [])):
            try:
                herdr.tab_close(tab_id)
                manifest["created_tabs"].remove(tab_id)
                actions.append(("closed-tab", tab_id, ""))
            except herdr.HerdrError as exc:
                actions.append(("keep-tab", tab_id, str(exc)))

    for workspace_id in list(manifest.get("created_workspaces", [])):
        if remove_worktrees:
            try:
                herdr.call(["worktree", "remove", "--workspace", workspace_id])
                manifest["created_workspaces"].remove(workspace_id)
                actions.append(("removed-worktree", workspace_id, ""))
                continue
            except herdr.HerdrError as exc:
                actions.append(("keep-worktree", workspace_id, str(exc)))
                continue
        if keep_panes:
            continue
        try:
            herdr.workspace_close(workspace_id)
            manifest["created_workspaces"].remove(workspace_id)
            actions.append(("closed-workspace", workspace_id, "worktree 内容保留在磁盘"))
        except herdr.HerdrError as exc:
            actions.append(("keep-workspace", workspace_id, str(exc)))

    manifest["state"] = manifest.get("state") or config.STATE_DONE
    runstore.save(manifest)
    return actions
