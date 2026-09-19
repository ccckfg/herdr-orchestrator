"""集中存放常量、默认值与角色库。

其他模块不得内联这些字面量；要调参数只改这一个文件。
"""

# ---------------------------------------------------------------- 目录与文件名

ORCH_DIR_NAME = ".herdr-orch"
# 用户用自然语言写的模型/agent 选用偏好。项目级优先，其次用户级。
# 脚本只负责找到它并原样交给编排器，不做任何解析——写法自由是重点。
MODELSELECT_FILENAME = "modelselect.md"
USER_ORCH_DIR = "~/.herdr-orch"
MANIFEST_NAME = "manifest.json"
TASK_FILE_NAME = "task.md"
TASKS_DIR_NAME = "tasks"
OUT_DIR_NAME = "out"
LOGS_DIR_NAME = "logs"
SUMMARY_NAME = "summary.md"
GITIGNORE_BODY = "# 由 herdr-orchestrator 自动生成：整个目录不进版本库\n*\n"

RUN_ID_TIME_FORMAT = "%Y%m%d-%H%M%S"

# ---------------------------------------------------------------- 注入子 agent 的环境变量

ENV_RUN_DIR = "HERDR_ORCH_RUN"
ENV_ROLE = "HERDR_ORCH_ROLE"
ENV_OUT = "HERDR_ORCH_OUT"

# herdr 自身注入的上下文
ENV_HERDR_ACTIVE = "HERDR_ENV"
ENV_HERDR_BIN = "HERDR_BIN_PATH"
ENV_HERDR_PANE = "HERDR_PANE_ID"
ENV_HERDR_TAB = "HERDR_TAB_ID"
ENV_HERDR_WORKSPACE = "HERDR_WORKSPACE_ID"

# ---------------------------------------------------------------- 超时与轮询

DEFAULT_SPAWN_TIMEOUT_MS = 60000      # agent start 等待就绪
DEFAULT_WATCH_TIMEOUT_S = 1800        # watch 整轮上限
DEFAULT_POLL_INTERVAL_S = 5           # 两次 snapshot 之间的间隔
STABLE_POLLS = 2                      # 结果文件连续 N 次大小不变才算写完
DEFAULT_PEEK_LINES = 120              # 诊断时从屏幕读回的行数
CLI_TIMEOUT_S = 120                   # 单条 herdr CLI 调用的硬超时

# agent start 返回"就绪"时，agent 的 TUI 可能还在画启动画面，这时投递会被吞掉。
# 投递前必须再等到 interactive_ready 且状态落定，然后留一点渲染余量。
SPAWN_READY_TIMEOUT_S = 90            # 等待 interactive_ready 的上限
READY_POLL_S = 1.0                    # 等待就绪时的轮询间隔
POST_READY_GRACE_S = 2.0              # 就绪后再留给 TUI 的渲染余量
ACTIVITY_GRACE_S = 12                 # 投递后多久内应当观察到 working
ACTIVITY_POLL_S = 1.0

# ---------------------------------------------------------------- 规模与布局

MAX_PARALLEL_ROLES = 4                # 单轮并发子 agent 上限
# 一个 tab 里最多容纳几个窗格（含主控和别人已有的）。超了就另开 tab：
# agent 的 TUI 在窄条窗格里会挤成一团，实测三列以上基本没法看。
MAX_PANES_IN_TAB = 3
SPLIT_DIRECTIONS = ("right", "down")  # 交替分割方向
TAB_LABEL_TEMPLATE = "orch:{run_id}"
WORKTREE_BRANCH_TEMPLATE = "orch/{run_id}-{role}"

# ---------------------------------------------------------------- 隔离模式

ISOLATION_SINGLE_WRITER = "single-writer"
ISOLATION_WORKTREE = "worktree"
ISOLATION_MODES = (ISOLATION_SINGLE_WRITER, ISOLATION_WORKTREE)
DEFAULT_ISOLATION = ISOLATION_SINGLE_WRITER

MODE_READ = "read-only"
MODE_WRITE = "write"

# ---------------------------------------------------------------- 自主程度

# 弹窗的正确解法是"让它不出现"，而不是事后猜该按哪个键。
# 这些参数在 agent start 时通过 `-- <args>` 传给各家 CLI 自己的开关。
AUTONOMY_ASK = "ask"      # 默认：保留各家原生审批，弹窗一律升级给人
AUTONOMY_AUTO = "auto"    # 放行审批，但保留各家的沙箱/工作区限制
AUTONOMY_YOLO = "yolo"    # 全绕过，包括沙箱和钩子信任
AUTONOMY_LEVELS = (AUTONOMY_ASK, AUTONOMY_AUTO, AUTONOMY_YOLO)
DEFAULT_AUTONOMY = AUTONOMY_ASK

# 实测自 2026-09-19 各 CLI 的 --help；换版本前先核一遍
KIND_AUTONOMY_ARGS = {
    "claude": {
        AUTONOMY_AUTO: ["--permission-mode", "acceptEdits"],
        AUTONOMY_YOLO: ["--dangerously-skip-permissions"],
    },
    "codex": {
        AUTONOMY_AUTO: ["--ask-for-approval", "never", "--sandbox", "workspace-write"],
        # --dangerously-bypass-hook-trust 专治 "Hooks need review" 那个弹窗
        AUTONOMY_YOLO: [
            "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust",
        ],
    },
    "droid": {
        AUTONOMY_AUTO: ["--auto", "medium"],
        AUTONOMY_YOLO: ["--auto", "high"],
    },
    "agy": {
        AUTONOMY_AUTO: ["--mode", "accept-edits"],
        AUTONOMY_YOLO: ["--dangerously-skip-permissions"],
    },
    # opencode / qodercli 的 CLI 没有对应开关，留空表示只能靠原生交互
    "opencode": {},
    "qodercli": {},
}

# 弹窗处置策略
ON_BLOCKED_ESCALATE = "escalate"  # 停手，交还用户（ask 档默认）
ON_BLOCKED_DECIDE = "decide"      # 抓屏交给编排器自己判断（auto/yolo 档默认）
ON_BLOCKED_POLICIES = (ON_BLOCKED_ESCALATE, ON_BLOCKED_DECIDE)
BLOCKED_CAPTURE_LINES = 60        # 抓弹窗时读回的屏幕行数

# ---------------------------------------------------------------- 角色状态机

STATE_PLANNED = "planned"
STATE_SPAWNED = "spawned"
STATE_DISPATCHED = "dispatched"
STATE_DONE = "done"
STATE_BLOCKED = "blocked"
STATE_TIMEOUT = "timeout"
STATE_FAILED = "failed"

TERMINAL_STATES = (STATE_DONE, STATE_BLOCKED, STATE_TIMEOUT, STATE_FAILED)

# herdr 上报的 agent 生命周期状态
AGENT_WORKING = "working"
AGENT_BLOCKED = "blocked"
AGENT_IDLE = "idle"
AGENT_DONE = "done"
AGENT_UNKNOWN = "unknown"
AGENT_SETTLED = (AGENT_IDLE, AGENT_DONE)

# ---------------------------------------------------------------- 角色库

ROLE_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"

# kinds 按优先级排列，spawn 时取第一个本机可用的
ROLE_LIBRARY = {
    "planner": {
        "mode": MODE_READ,
        "kinds": ("claude", "codex", "agy"),
        "summary": "拆解任务、给出执行顺序与风险点，不碰代码",
    },
    "researcher": {
        "mode": MODE_READ,
        "kinds": ("agy", "claude", "codex"),
        "summary": "查资料、读代码、回答事实性问题，不碰代码",
    },
    "implementer": {
        "mode": MODE_WRITE,
        "kinds": ("claude", "codex", "droid"),
        "summary": "实际写代码；single-writer 模式下全场唯一写入者",
    },
    "reviewer": {
        "mode": MODE_READ,
        "kinds": ("codex", "agy", "claude"),
        "summary": "审查 diff 或指定文件，只报可执行的问题",
    },
    "tester": {
        "mode": MODE_READ,
        "kinds": ("droid", "opencode", "codex"),
        "summary": "跑测试与构建，回报失败用例和复现命令",
    },
    "docs": {
        "mode": MODE_WRITE,
        "kinds": ("claude", "agy", "codex"),
        "summary": "写文档；可写范围限定在文档目录",
    },
}

# herdr kind -> 本机可执行文件名，用于探测哪些 kind 真能起得来
KIND_EXECUTABLES = {
    "claude": "claude",
    "codex": "codex",
    "droid": "droid",
    "agy": "agy",
    "opencode": "opencode",
    "gemini": "gemini",
    "cursor": "cursor-agent",
    "copilot": "copilot",
    "qwen": "qwen",
    "kimi": "kimi",
    "amp": "amp",
    "grok": "grok",
    "qodercli": "qoder",
    "pi": "pi",
    "kilo": "kilo",
    "cline": "cline",
    "devin": "devin",
}

# ---------------------------------------------------------------- 交付协议

# 附加到每张任务卡末尾，保证子 agent 一定拿到回传约定
PROTOCOL_FOOTER = """
---

## 交付协议（编排器自动附加，必须遵守）

1. 最终结果写入这个文件（绝对路径）：
   `{out_path}`
2. 结果文件是 Markdown，首行为 `# {role} result`，至少包含这几个小节：
   `## 结论` / `## 依据` / `## 变更文件` / `## 遗留问题`
3. 写完后在终端**只回复一行**：`DONE {out_path}`
4. 可写范围：{write_scope}。范围之外的文件一律不许创建、修改或删除。
5. 遇到需要审批、确认或你无法自行决定的事：**停下**，把问题写进结果文件的
   `## 阻塞` 小节，然后回复一行 `BLOCKED {out_path}`，不要擅自选择。
6. 不要运行 `herdr`（会被拒绝），不要去看或干预其他窗格。

编排器靠结果文件判定完成，不靠屏幕内容。文件没落盘就等于没完成。
"""

WRITE_SCOPE_READ_ONLY = "只读。除结果文件外不得修改任何文件"
WRITE_SCOPE_FULL = "当前工作目录下的项目文件"
WRITE_SCOPE_WORKTREE = "仅限你自己的 worktree：{path}"

DISPATCH_PROMPT_TEMPLATE = (
    "Read the task card at {card_path} and follow it exactly. "
    "Do not ask me for confirmation; the card is complete."
)
