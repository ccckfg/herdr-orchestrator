# herdr-orchestrator

让一个 AI 编程助手在 [Herdr](https://herdr.dev) 里当**包工头**：把活拆开，在旁边的终端窗格里
起真实的 codex / droid / agy / claude 进程，同时干，干完把结果汇总给你。

一句话区别：这不是"一个模型假装成好几个角色"，而是**真的同时开几个不同厂商的 CLI**，
各自独立上下文、独立模型。让 claude 写、codex 审，才是真的交叉审查。

```
┌─ 你的窗格 ──────────┬─ reviewer (codex) ──┐
│ claude = 编排者     │ 正在审代码…          │
│ 拆任务 / 派活 / 汇总 ├─ tester (droid) ────┤
│                     │ 正在跑测试…          │
└─────────────────────┴─────────────────────┘
```

## 什么时候值得用

- **交叉审查**：让 claude 写的代码交给 codex 审——换一家的模型，才看得出问题
- **多视角并行**：审代码、跑测试、查资料三件事同时开工，不用排队
- **长任务**：派出去之后你该干嘛干嘛，窗格在后台跑，关掉终端也不会断

## 什么时候别用

- 你自己几分钟能干完的活。**起一个子 agent 的成本远比你自己动手高**
- 只是想开个后台终端跑命令——那直接用 `herdr pane run` 就行

## 开始之前

| 需要 | 说明 |
| --- | --- |
| [Herdr](https://herdr.dev/zh-cn/docs/install/) | 终端工作区管理器，这个 skill 只能在它里面跑 |
| 至少 2 个 agent CLI | claude / codex / droid / agy / opencode 任选，装得越多能派的角色越多 |
| Python 3.9+ | 脚本零依赖，只用标准库 |

装完 Herdr 之后，在项目目录里敲 `herdr` 进入，再在窗格里启动你的主力 agent（比如 `claude`）。

## 安装

```bash
npx skills add ccckfg/herdr-orchestrator --skill herdr-orchestrator -g
```

或者手动装（想让源码可改）：

```bash
git clone https://github.com/ccckfg/herdr-orchestrator.git
# macOS / Linux
ln -s "$PWD/herdr-orchestrator" ~/.claude/skills/herdr-orchestrator
# Windows（未开开发者模式时用目录联接，不需要管理员权限）
cmd /c mklink /J "%USERPROFILE%\.claude\skills\herdr-orchestrator" "%CD%\herdr-orchestrator"
```

装完自检一下：

```bash
python ~/.claude/skills/herdr-orchestrator/scripts/orch.py doctor
```

它会告诉你：在不在 Herdr 里、本机**实际**能起哪些 agent、是不是 git 仓库。
「可用 kind」这一行是扫 PATH 实测出来的，以它为准。

## 告诉它你想用哪些模型

写一份 `modelselect.md`，**用大白话写**就行，不需要任何格式：

```markdown
# 我的选型偏好

- 复杂任务（架构、重构、难 bug）：droid 的 kimi-k3，强度 max
- 简单任务（改字符串、加注释、跑测试）：droid 的 glm-5.3-flash
- 要快的：agy 的 gemini-3.8-flash，effort high
- 代码审查：一律用 codex，别用写代码那个模型审自己
- 别用 opencode，我没配 provider
```

放在这两个位置之一（项目级优先，可以给不同项目配不同偏好）：

```
<你的项目>/.herdr-orch/modelselect.md
~/.herdr-orch/modelselect.md
```

**脚本不解析这个文件**——是编排器自己读懂它，再翻译成给各个 CLI 的真实参数。
所以你怎么写都行，包括写条件（"跑测试用最便宜的，反正只是看红绿"）。
没写的话它会用默认选型，并在开工前提醒你写一份。

> droid 有个特殊情况：它的**交互模式没有 `--model` 参数**（只有 `droid exec` 有）。
> 编排器会自动生成一份临时设置文件用 `--settings` 传进去，效果一样，已实测可用。

## 最简单的用法：说人话

装好之后，**你基本不需要记任何命令**。直接跟你的 agent 说：

> 用 herdr-orchestrator 起一个 codex 帮我审一下刚才改的代码

> 派两个 agent 并行分析这个项目：一个看架构，一个跑测试

skill 会自动加载，它自己知道该调哪些脚本、怎么写任务卡、怎么等结果。
你只要在它问你的时候回答就行——比如某个子 agent 弹出确认框的时候。

## 手动用（想知道底下发生了什么）

```bash
S=~/.claude/skills/herdr-orchestrator/scripts/orch.py

# 1. 自检
python $S doctor

# 2. 建一次编排任务（run），指定角色和用哪个 CLI
python $S new --role reviewer:codex --role tester:droid --task 任务描述.md

# 3. 给每个角色写任务卡（交付协议会自动附加到卡尾）
python $S card --role reviewer --file reviewer任务.md
python $S card --role tester   --file tester任务.md

# 4. 建窗格 + 启动 agent
python $S spawn

# 5. 把任务卡发过去（不阻塞）
python $S dispatch

# 6. 等它们干完（一次等全部，不是一个个排队）
python $S watch --timeout 900

# 7. 汇总结果
python $S collect --print-summary

# 8. 关掉自己开的窗格（只关自己开的）
python $S cleanup
```

所有产物都在项目下的 `.herdr-orch/<run-id>/`，这个目录会自我忽略，不会污染你的提交。

## 要不要一直点确认：三档自主程度

子 agent 动不动就弹「要执行这个命令吗？」很烦。`new` 的时候可以选：

| 档位 | 效果 | 怎么开 |
| --- | --- | --- |
| `ask`（默认） | 保留各家原生审批，弹窗交给你 | 什么都不加 |
| `auto` | 放行审批，**但沙箱还在** | `--autonomy auto` |
| `yolo` | 全绕过，连沙箱一起关 | `--yolo` |

做法是启动时就带上各家自己的开关（claude 的 `--dangerously-skip-permissions`、
codex 的 `--dangerously-bypass-approvals-and-sandbox` 等），**让弹窗根本不出现**，
而不是事后去猜该按哪个键。

⚠️ **`yolo` 关掉的不只是弹窗，还有沙箱。** 子 agent 可以执行任意命令、改任意文件，没有东西拦它。
只读角色（审代码、跑测试）用它很划算；让 agent 写代码又开 yolo，建议配 `--isolation worktree`
把改动隔离到独立分支；碰生产配置和密钥就别用了。

有三类弹窗**任何档位都绕不过**：版本更新提示、登录过期、首次目录信任。
遇到这种，`watch` 会把弹窗内容抓给你看，然后：

```bash
python $S answer --role reviewer 2     # 看清楚了再按，别盲按
```

故意没做"自动盲按"：codex 的钩子弹窗里 `1` 是"去审查"、`2` 才是"信任并继续"，
而同一时刻的更新提示里 `2` 是"跳过"。顺序各家不同，必须有个会读字的先看一眼。

## 多个 agent 同时改代码怎么办

它们互相看不见，同时写同一个文件必然互相覆盖，而且**谁都不会报错**。两种办法：

- **`single-writer`（默认）**：只允许一个角色可写，其余只读并行。零冲突，不需要 git
- **`worktree`**：每个写入者一棵独立 git worktree + 分支，最后你自己合并。需要是 git 仓库

配两个可写角色又选 `single-writer` 会被直接拒绝——故意的，免得你以为没事。

## 它怎么知道子 agent 干完了

**看文件，不看屏幕。** 每个子 agent 收到的任务卡末尾都有一段协议，要求它：

1. 把结果写进指定的绝对路径
2. 写完在终端只回一行 `DONE <路径>`
3. 遇到搞不定的事，写进结果文件的「阻塞」小节，回 `BLOCKED <路径>`

编排器靠**结果文件落盘且大小稳定**判完成。不看 agent 状态——Herdr 的 `idle` / `done`
只表示"能接受输入"，不代表活干完了。屏幕内容只用来排查问题（`orch.py peek`），
因为屏幕会截断、会被 TUI 重绘搅乱。

## 内置角色

| 角色 | 读写 | 默认挑谁 |
| --- | --- | --- |
| `planner` | 只读 | claude → codex → agy |
| `researcher` | 只读 | agy → claude → codex |
| `reviewer` | 只读 | codex → agy → claude |
| `tester` | 只读 | droid → opencode → codex |
| `implementer` | 可写 | claude → codex → droid |
| `docs` | 可写 | claude → agy → codex |

不写 kind 就按优先级挑一个本机装了的。也可以随便起名字：`--role 探针:droid`（默认只读）。
一轮最多 4 个，多了拆成几轮。

## 遇到问题

| 现象 | 怎么办 |
| --- | --- |
| 第一次起某个 agent 就卡住 | 多半是它的首次信任/更新弹窗。`peek` 看一眼，答一次以后就不问了 |
| 任务发出去了但对方没反应 | 可能被 agent 的启动画面吞了。`peek` 看输入框是不是空的，是就 `dispatch --force` |
| 结果文件一直不出现 | 任务卡里没说清要产出什么，或者它在等人回答 |
| `yolo` 了还是弹窗 | 更新/登录/信任这类绕不过，用 `answer` 回应 |
| 提示某个 kind 没有 yolo 开关 | opencode、qodercli 的 CLI 确实没有，只能手动应付它的弹窗 |

**重投之前一定先看屏幕**：超时不等于没发过去。如果它其实收到了正在慢慢干，
重投会让同一件事做两遍——可写角色身上就是两次改动叠加。

更全的对照表在 `references/troubleshooting.md`。

## 目录结构

```
herdr-orchestrator/
├── SKILL.md                    # agent 读的主文件：什么时候用、怎么编排、安全红线
├── references/
│   ├── commands.md             # 每个子命令的完整参数
│   ├── protocol.md             # run 目录、任务卡/结果卡结构、完成判定
│   ├── roles.md                # 角色库、怎么挑 CLI、任务卡模板
│   ├── isolation.md            # 两种隔离模式的取舍
│   ├── autonomy.md             # 三档自主程度、各家绕过参数、yolo 的代价
│   ├── modelselect.md          # 选型偏好怎么读、怎么落成参数、droid 的特殊处理
│   └── troubleshooting.md      # 故障对照表
└── scripts/
    ├── orch.py                 # 命令行入口
    └── orchlib/                # 实现：herdr 封装 / 布局 / 派活 / 等待 / 汇总 / 清理
```

## 已知限制

- **`worktree` 模式没有实跑验证过**（开发时的目录不是 git 仓库）。代码按防御性写的，第一次用建议盯着点
- 只在 **Windows 11 + Herdr 0.9.1** 上测过。macOS / Linux 理论上没问题，但没验证
- 各家 CLI 的绕过参数记录于 2026-09-19，**换版本前请核对** `scripts/orchlib/config.py` 里的 `KIND_AUTONOMY_ARGS`
- "只读角色"是任务卡里的约定，靠子 agent 自觉，**不是沙箱**。要强隔离请用 `worktree`

## 致谢

建立在 [Herdr](https://herdr.dev) 的 CLI 和 socket API 之上。
Herdr 官方也提供一个 [herdr skill](https://github.com/herdrdev/herdr/blob/master/skills/herdr/SKILL.md)
教 agent 控制 Herdr——那份管"怎么操作 Herdr"，这份管"怎么把几个 agent 组织起来干活"，建议一起装。
