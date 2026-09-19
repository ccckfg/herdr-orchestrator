"""窗格分配：决定子 agent 住在哪里，并登记创建了什么好让 cleanup 有据可依。

规则来自 herdr 官方 skill：宽窗格往右分、窄窗格往下分，不重复同向分割，
全程 --no-focus 不抢用户焦点。超过两个子 agent 就另开 tab，否则会挤成窄条。
"""

from . import config, herdr


def _geometry(pane_id):
    """尽力取窗格宽高；拿不到就返回 None，交给调用方用默认方向。"""
    try:
        data = herdr.pane_layout(pane_id)
    except herdr.HerdrError:
        return None
    for holder in (data, data.get("layout"), data.get("pane"), data.get("rect")):
        if not isinstance(holder, dict):
            continue
        width = holder.get("width") or holder.get("cols") or holder.get("columns")
        height = holder.get("height") or holder.get("rows")
        if width and height:
            return float(width), float(height)
    return None


def initial_direction(pane_id):
    geometry = _geometry(pane_id)
    if not geometry:
        return config.SPLIT_DIRECTIONS[0]
    width, height = geometry
    # 终端字符是竖长的，用 2:1 折算成视觉比例再判断宽窄
    return "right" if width >= height * 2 else "down"


def _pane_id(pane):
    return pane.get("pane_id") if isinstance(pane, dict) else None


def _panes_in_tab(tab_id):
    """统计某个 tab 现有窗格数；查不到就按 1 算（只有主控自己）。"""
    if not tab_id:
        return 1
    try:
        snap = herdr.snapshot()
    except herdr.HerdrError:
        return 1
    panes = [
        pane for pane in snap.get("panes", []) if pane.get("tab_id") == tab_id
    ]
    return len(panes) or 1


def _pick(result, *keys):
    for key in keys:
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return {}


class PaneAllocator:
    """按需产出空闲窗格。总数决定用当前 tab 还是新开 tab。"""

    def __init__(self, manifest, total):
        self.manifest = manifest
        self.total = total
        # 当前 tab 里已经有几个窗格（包括别人开的）要一起算，否则会挤成窄条
        existing = _panes_in_tab(manifest.get("owner_tab_id"))
        self.use_new_tab = existing + total > config.MAX_PANES_IN_TAB
        self.tab_id = None
        self.last_pane = None
        self.index = 0
        self._first_direction = None

    def _record_pane(self, pane_id):
        if pane_id and pane_id not in self.manifest["created_panes"]:
            self.manifest["created_panes"].append(pane_id)

    def _direction(self):
        if self.index == 0 and not self.use_new_tab:
            if self._first_direction is None:
                self._first_direction = initial_direction(
                    self.manifest["owner_pane_id"]
                )
            return self._first_direction
        # 交替方向，避免连续同向分割把窗格挤成没法用的窄条
        return config.SPLIT_DIRECTIONS[self.index % len(config.SPLIT_DIRECTIONS)]

    def next_pane(self, cwd, env):
        if self.use_new_tab and self.index == 0:
            tab, root = herdr.tab_create(
                self.manifest["owner_workspace_id"],
                cwd=cwd,
                label=config.TAB_LABEL_TEMPLATE.format(run_id=self.manifest["run_id"]),
                env=env,
            )
            self.tab_id = tab.get("tab_id")
            if self.tab_id:
                self.manifest["created_tabs"].append(self.tab_id)
            pane_id = _pane_id(root)
            self._record_pane(pane_id)
            self.last_pane = pane_id
            self.index += 1
            return {
                "pane_id": pane_id,
                "tab_id": self.tab_id,
                "workspace_id": self.manifest["owner_workspace_id"],
            }

        source = self.last_pane or self.manifest["owner_pane_id"]
        pane = herdr.pane_split(source, self._direction(), cwd=cwd, env=env)
        pane_id = _pane_id(pane)
        if not pane_id:
            raise herdr.HerdrError("pane split 没有返回 pane_id", code="layout_no_pane")
        self._record_pane(pane_id)
        self.last_pane = pane_id
        self.index += 1
        return {
            "pane_id": pane_id,
            "tab_id": pane.get("tab_id") or self.tab_id,
            "workspace_id": pane.get("workspace_id")
            or self.manifest["owner_workspace_id"],
        }


def allocate_worktree(manifest, role_name, trust=False):
    """给写入型角色开一棵独立 worktree，返回其中的窗格位置。

    herdr 会把 worktree 挂成一个独立 workspace，清理时必须连带关掉。
    """
    branch = config.WORKTREE_BRANCH_TEMPLATE.format(
        run_id=manifest["run_id"], role=role_name
    )
    result = herdr.worktree_create(
        manifest["cwd"], branch=branch, label=branch, trust=trust
    )
    workspace = _pick(result, "workspace", "created_workspace")
    root = _pick(result, "root_pane", "pane")
    workspace_id = workspace.get("workspace_id")
    pane_id = _pane_id(root)
    if not workspace_id or not pane_id:
        raise herdr.HerdrError(
            "worktree create 返回里找不到 workspace/root_pane：{}".format(result),
            code="worktree_shape",
        )
    manifest["created_workspaces"].append(workspace_id)
    manifest["created_panes"].append(pane_id)
    path = (
        result.get("path")
        or _pick(result, "worktree").get("path")
        or workspace.get("cwd")
    )
    return {
        "pane_id": pane_id,
        "tab_id": workspace.get("active_tab_id"),
        "workspace_id": workspace_id,
        "worktree": {"branch": branch, "path": path, "workspace_id": workspace_id},
    }
