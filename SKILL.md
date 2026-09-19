---
name: herdr-orchestrator
description: "在 Herdr 里把自己变成多 agent 编排者：拆任务、在旁边窗格起 claude/codex/droid/agy 等真实 CLI agent、并发派活、回收结果、汇总。仅在用户明确要求多 agent 协同、并行编排、交叉审查（类似 ultrareview 的扇出）时使用；单个 agent 能干完的活不要用。要求 HERDR_ENV=1。"
---

# Herdr 多 agent 编排器

你是编排者。子 agent 是本机真实的 CLI 进程，住在 Herdr 窗格里，各自有独立上下文，
看不见你的对话。它们只能通过**任务卡**收活、通过**结果文件**交活。

配套脚本：`scripts/orch.py`（零依赖 Python 3.9+）。先读本文，细节查 `references/`。

## 开工前

```bash
python <skill-dir>/scripts/orch.py doctor
```

`HERDR_ENV≠1` 就停下，告诉用户本工具只能在 Herdr 窗格里跑。
doctor 会列出本机真正起得来的 kind——**别照着文档猜，以它的输出为准**。

## 什么时候用

用：交叉审查（一个写、另一个独立审）、多视角并行分析、跨厂商对照、
需要长时间跑又不想占住自己的活。

不用：你自己几分钟能干完的；只是想开个后台终端跑命令（那直接 `herdr pane run`）；
用户没提多 agent 协同。**起一个子 agent 的成本远高于你自己动手**，别为了用而用。

## 核心模型

一次编排 = 一个 **run**，落在 `<项目>/.herdr-orch/<run-id>/`：

```
tasks/<角色>.md   你写的任务卡（脚本自动附加交付协议）
out/<角色>.md     子 agent 写的结果卡  ← 唯一的完成依据
logs/<角色>.log   屏幕快照，只用于诊断
summary.md        collect 汇总，你读这一个就够
manifest.json     状态与清理清单
```

三条判定规则，违反了整个编排就会失灵：

1. **完成 = 结果文件落盘且大小稳定**。不看 agent 状态：herdr 的 `idle`/`done`
   只表示"能接受输入"，`unknown` 更不代表干完了。
2. **结果只从文件读，不从屏幕读**。屏幕会截断、会被 TUI 重绘搅乱。
   `peek` 出来的东西只能用来诊断，不能当结果。
3. **`blocked` 怎么处理取决于自主档**。默认 `ask` 档下读出来问用户、绝不代答；
   `auto` / `yolo` 档下由你读屏后自己决定（见下面「自主档位」）。

## 编排主循环

```bash
S=<skill-dir>/scripts/orch.py

python $S doctor                                          # 1 自检
python $S new --role reviewer:codex --role tester:droid \
             --task task.md --isolation single-writer \
             --autonomy ask                               # 2 建 run
python $S card --role reviewer --file -                   # 3 逐个写任务卡（stdin）
python $S spawn                                           # 4 建窗格 + 起 agent
python $S dispatch                                        # 5 投递（非阻塞）
python $S watch --timeout 900                             # 6 并发等待
python $S collect --print-summary                         # 7 汇总
python $S cleanup                                         # 8 收尾
```

`spawn` 和 `dispatch` 分开不是多此一举：起进程慢且容易卡在首启弹窗，
分开才能在投递前逐个确认对方真的能吃输入。

需要二轮时：改写任务卡 → `dispatch --force --role <角色>` → 再 `watch`。

## 写任务卡

卡是子 agent 唯一的信息来源，**它看不到你的上下文**。每张卡必须：

- **自包含**：背景、要做什么、判定标准，一次说全。不要写"按之前说的"。
- **给绝对路径**：它的 cwd 可能和你不同（worktree 模式下一定不同）。
- **限定产出**：要它给结论和依据，不要它在终端里长篇输出——结果走文件。
- **不许反问**：卡里明确"不要问我，按卡执行"。子 agent 问你，你也听不见。

交付协议（写结果文件、DONE/BLOCKED 回执、可写范围）由 `card` 命令自动附加到卡尾，
**你不用也不要自己写**。模板和角色分工见 `references/roles.md`。

## 角色与 kind

`--role 名字[:kind[:read-only|write]]`。不写 kind 就按角色库的优先级挑一个本机可用的。

内置角色：`planner` `researcher` `reviewer` `tester`（只读）、`implementer` `docs`（可写）。
角色名随便起也行，默认按只读处理。

选 kind 的经验：让**写代码的和审代码的不是同一个 kind**，交叉审查才有意义；
跑测试挑启动快的。一轮最多 4 个，多了就拆轮次。

## 选隔离模式

你自己判断，用户有明确要求就听用户的：

- **`single-writer`（默认）**：最多一个角色可写，其余只读并行。零冲突，不需要 git。
  绝大多数情况选它。
- **`worktree`**：每个写入者一棵独立 git worktree + 分支，最后由用户合并。
  只在「多个写入任务彼此独立」且「目录是 git 仓库」时才用。
  `--trust-repository` 只有在用户确认过仓库可信之后才加。

两个写入者 + `single-writer` 会被脚本直接拒绝——这是有意的。详见 `references/isolation.md`。

## 自主档位

决定子 agent 要不要向人确认。`new --autonomy {ask,auto,yolo}`，`--yolo` 是第三档的简写。

| 档位 | 做什么 | 弹窗怎么办 |
| --- | --- | --- |
| `ask`（默认） | 保留各家原生审批 | 停手，交还用户 |
| `auto` | 放行审批，保留沙箱 | 你读屏后自己决定 |
| `yolo` | 全绕过，含沙箱和钩子信任 | 你读屏后自己决定 |

实现方式是启动时带上各家 CLI 自己的开关（claude 的 `--dangerously-skip-permissions`、
codex 的 `--dangerously-bypass-approvals-and-sandbox` 等），**让弹窗不出现**，
而不是事后猜该按哪个键。没有对应开关的 kind（opencode、qodercli）仍会弹，`spawn` 会明说。

有两类弹窗任何开关都绕不过：**版本更新提示、登录鉴权、首次目录信任**。
`auto`/`yolo` 档下 `watch` 会把弹窗原文抓回来给你，然后走这个循环：

```bash
python $S watch --timeout 600      # 返回 blocked，附弹窗原文
python $S answer --role probe 2    # 读懂之后回应；先读再按，选项顺序各家不同
python $S watch --timeout 600      # 继续等
```

**没有盲按模式**，这是故意的：codex 钩子弹窗里 `1` 是"去审查"、`2` 才是"信任并继续"，
而同一时刻的更新提示里 `2` 是"Skip"。必须有个会读字的东西先看一眼。

选档位的判断：只读角色用 `yolo` 收益最大、风险可控；可写角色配 `yolo` 就搭 `worktree`；
非 git 目录里的可写角色优先 `auto`（沙箱还在）；碰生产配置、密钥、部署脚本不要用 `yolo`。
细节和各 kind 参数表见 `references/autonomy.md`。

## 安全红线

- `ask` 档下，子 agent 的审批框、信任提示、危险操作确认**一律交还用户**，不替它选。
  `auto` / `yolo` 是用户明确要求才开的档，那时才由你决定——**但仍然要先读屏再按键**。
- 只清理 manifest 里登记过的窗格/tab/workspace。别人的窗格一律不碰。
- 不运行 `herdr server stop`，不杀 Herdr 主进程，不关用户的 workspace。
- 投递超时**不等于**没投递成功。先 `peek` 看屏幕，确认没进去再 `--force` 重投，
  否则会重复执行一遍任务。
- 全程 `--no-focus`：用户的焦点是用户的，编排不抢。
- `cleanup` 默认保留 worktree 里的改动，`--remove-worktrees` 会丢掉未合并的工作，
  必须用户明确要求才加。

## 出事了看哪

| 现象 | 去处 |
| --- | --- |
| `spawn` 报 blocked / agent_not_ready | 首启弹窗，`peek` 看是什么；ask 档交用户，auto/yolo 档用 `answer` |
| yolo 档下还是弹窗 | 更新提示/登录/目录信任这类绕不过，只能 `answer` |
| `dispatch` 提示没观察到 working | 任务卡可能被启动画面吞了，`peek` 确认后 `--force` |
| `watch` 超时且全程没 working | 同上，多半没投进去 |
| 结果文件一直不出现 | 卡里没写清产出要求，或子 agent 在等人回答 |
| worktree 相关报错 | 不是 git 仓库，或需要用户确认仓库信任 |

完整对照表和处置动作在 `references/troubleshooting.md`。

## 参考文件

- `references/commands.md` — orch.py 每个子命令的参数与示例
- `references/protocol.md` — run 目录、任务卡/结果卡结构、完成判定细节
- `references/roles.md` — 角色库、kind 路由、任务卡模板
- `references/isolation.md` — 两种隔离模式的取舍与 worktree 用法
- `references/autonomy.md` — 三档自主程度、各 kind 的绕过参数、yolo 的代价
- `references/troubleshooting.md` — 故障对照表
