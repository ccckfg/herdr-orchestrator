# 交付协议与 run 目录

编排能不能跑通，全看这一套约定。它解决的是一个硬限制：
**子 agent 的输出只能通过终端屏幕回来，而屏幕不可靠**——会截断、会被 TUI 重绘搅乱、
长回答读不全。所以结果一律走文件，屏幕只留给诊断。

## run 目录

```
<项目>/.herdr-orch/
├── .gitignore            # 内容是 *，整个目录自我忽略，不动项目自己的 .gitignore
└── <run-id>/             # 形如 20260919-203154-6e7b
    ├── manifest.json     # run 状态机 + 清理清单
    ├── task.md           # 总任务，留档用
    ├── tasks/<角色>.md   # 任务卡（正文由你写，协议由脚本附加）
    ├── out/<角色>.md     # 结果卡，子 agent 写 ← 唯一完成依据
    ├── logs/<角色>.log   # peek 抓下来的屏幕快照
    └── summary.md        # collect 产出
```

run-id 是时间戳加随机后缀，天然按时间排序，`--run` 不指定时取最新的。

## manifest.json

| 字段 | 用途 |
| --- | --- |
| `isolation` | `single-writer` / `worktree` |
| `owner_pane_id` / `owner_tab_id` / `owner_workspace_id` | 你自己的位置，分割窗格和清理时用来避让 |
| `roles[]` | 每个角色的 kind、模式、窗格、状态、错误、worktree 信息 |
| `created_panes` / `created_tabs` / `created_workspaces` | **清理的唯一依据**，没登记的一律不碰 |

角色状态机：

```
planned → spawned → dispatched → done
                              ↘ blocked / timeout / failed
```

## 注入子 agent 的环境变量

`spawn` 建窗格时通过 `herdr pane split --env` 注入：

| 变量 | 内容 |
| --- | --- |
| `HERDR_ORCH_RUN` | run 目录绝对路径 |
| `HERDR_ORCH_ROLE` | 角色名 |
| `HERDR_ORCH_OUT` | 该角色结果文件的绝对路径 |

注意：`worktree` 模式下的窗格由 `herdr worktree create` 创建，**它不支持 `--env`**，
所以那些窗格里没有这几个变量。任务卡里的绝对路径才是可靠来源，
环境变量只是锦上添花——**不要把协议建立在环境变量一定存在的假设上**。

## 任务卡的结构

正文由你写，卡尾这段由 `orch.py card` 自动附加（内容见 `scripts/orchlib/config.py`
的 `PROTOCOL_FOOTER`，要改口径改那里）：

1. 结果写进指定的绝对路径
2. 结果是 Markdown，首行 `# <角色> result`，含 `## 结论` / `## 依据` / `## 变更文件` / `## 遗留问题`
3. 写完在终端只回一行 `DONE <path>`
4. 声明可写范围，范围外一律不许碰
5. 遇到要审批、要确认、自己定不了的事：停下，写进 `## 阻塞`，回 `BLOCKED <path>`
6. 不许运行 `herdr`，不许去看或干预别的窗格

第 5 条是关键：它把"子 agent 卡住"从一个需要你猜的状态，变成一个可读的文件。

## 完成判定

`watch` 按这个顺序判，每轮一次 `herdr api snapshot`（一次调用拿到所有 agent 状态）：

1. agent 状态是 `blocked` → 标记 `blocked`，**立刻停止等待，交给用户**。
   它卡在真实的审批对话框上，不是你能替它按的。
2. agent 从快照里消失（窗格被关 / 进程退出）→ 有结果文件算 `done`，没有算 `failed`。
3. 结果文件存在、非空、且**连续两轮大小不变** → `done`。
   要求大小稳定是为了避开读到写了一半的文件。
4. 整轮超时 → `timeout`，并附上"全程有没有观察到 working"作为诊断线索。

**不要拿 agent 状态当完成信号**：herdr 的 `idle` 和 `done` 都只表示"能接受输入"，
区别仅在于有没有被人看过；`unknown` 表示 herdr 认不出来，更不代表干完了。

## 为什么投递只发一句话

`dispatch` 发给子 agent 的原文是：

```
Read the task card at <绝对路径> and follow it exactly. Do not ask me for confirmation; the card is complete.
```

任务正文全在文件里。这样做的好处：绕开命令行长度和引号转义（中文、换行、反引号
在 Windows 上尤其容易出事），也让改派只需要重写文件。

## 时序上的坑

`herdr agent start` 返回"就绪"时，agent 的 TUI 可能还在画启动画面，
**这时投进去的文字会被整段吞掉**（实测 droid 就这样丢了一整张任务卡，
屏幕上输入框依然空着，agent 状态一直 `idle`）。

所以 `dispatch` 在投递前会：轮询到 `interactive_ready` 为真且状态落定 → 再等 2 秒渲染余量 →
才提交。提交后再盯 12 秒，看有没有进入 `working`，没有就警告。

反过来也要记住：**没观察到 working 不等于没投递成功**。先 `peek` 看屏幕，
确认输入框是空的、没有已提交的内容，再 `--force` 重投，否则任务会被执行两遍。
