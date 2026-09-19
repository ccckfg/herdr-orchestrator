# 自主档位（含 yolo）

弹窗的正确解法是**让它根本不出现**，而不是事后去猜该按哪个键。
所以自主档位在 `agent start` 时就把各家 CLI 自己的开关带上，
通过 `herdr agent start ... -- <原生参数>` 传递。

## 三档

| 档位 | 含义 | 弹窗策略 |
| --- | --- | --- |
| `ask`（默认） | 保留各家原生审批 | `escalate`：停手，交还用户 |
| `auto` | 放行审批，**保留沙箱/工作区限制** | `decide`：抓屏交编排器判断 |
| `yolo` | 全绕过，含沙箱与钩子信任 | `decide` |

```bash
python "$S" new --role impl:claude:write --autonomy auto
python "$S" new --role probe:codex --yolo          # --yolo 等价于 --autonomy yolo
```

档位是 run 级属性，写进 manifest，`spawn` 时生效。

## 各 kind 实际带的参数

实测自 2026-09-19 各 CLI 的 `--help`。换版本前核一遍，表在 `config.py` 的 `KIND_AUTONOMY_ARGS`。

| kind | `auto` | `yolo` |
| --- | --- | --- |
| claude | `--permission-mode acceptEdits` | `--dangerously-skip-permissions` |
| codex | `--ask-for-approval never --sandbox workspace-write` | `--dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust` |
| droid | `--auto medium` | `--auto high` |
| agy | `--mode accept-edits` | `--dangerously-skip-permissions` |
| opencode | 无 | 无 |
| qodercli | 无 | 无 |

**没有对应开关的 kind 仍然会弹自己的审批框。** `spawn` 会在输出里明说
（`! kind=opencode 没有 yolo 档开关`），不要以为设了 yolo 就万事大吉。

## 绕不过的那一类弹窗

权限开关只管**权限**。这些东西照样挡在前面：

- 版本更新提示（codex 的 "Update available"——实测在 yolo 档下依然出现）
- 登录 / 鉴权过期
- 首次运行的目录信任、条款确认
- agent 自己的引导流程

这类只能靠 `answer` 回应。所以 `auto` / `yolo` 档的弹窗策略是 `decide` 而不是"无视"。

## decide 循环

`auto` / `yolo` 档下 `watch` 遇到 `blocked` 时：抓屏存进 `logs/<角色>.log` →
把弹窗原文一起返回 → 结束对该角色的等待。然后编排器自己走这个循环：

```bash
python "$S" watch --timeout 600          # 返回 blocked，附弹窗原文
python "$S" peek --role probe            # 需要更多上下文时再看一眼
python "$S" answer --role probe 2        # 读懂之后按需回应
python "$S" watch --timeout 600          # 继续等
```

`answer` 后状态会退回被卡住之前那一档：没投过任务卡的回 `spawned`，
投过的回 `dispatched`，所以不会漏发任务卡，也不会重复投递。

## 为什么没有"盲按"模式

因为选项顺序各家不一样，盲按必然选错。实测那个 codex 钩子弹窗：

```
› 1. Review hooks
  2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

按 1 是进另一个审查界面，按 3 是继续但钩子不生效（herdr 的状态上报就废了），
只有 2 是想要的。同一时刻的更新提示里，2 又是 "Skip"。

**先读屏，再决定按什么。** 这一步必须有个会读字的东西在，
`decide` 档下那个东西是编排器自己，`ask` 档下是用户。

## yolo 的真实代价

`yolo` 不只是"不弹窗"，它连沙箱一起关掉：

- codex 的 `--dangerously-bypass-approvals-and-sandbox` 原文写着
  "EXTREMELY DANGEROUS. Intended solely for running in environments that are externally sandboxed"。
- claude 的 `--dangerously-skip-permissions` 跳过全部权限检查。
- 这意味着子 agent 可以执行任意命令、改任意文件，没有任何东西拦它。

搭配建议：

| 场景 | 建议 |
| --- | --- |
| 只读角色（reviewer/tester/researcher） | `yolo` 风险可控，收益最大——省掉一堆确认 |
| 可写角色 + git 仓库 | `yolo` 配 `--isolation worktree`，改动隔离在独立分支 |
| 可写角色 + 非 git 目录 | 优先 `auto`：沙箱还在，出事有边界 |
| 碰生产配置、密钥、部署脚本 | 别用 `yolo` |

`new` 命令在 `yolo` + 可写角色 + 非 worktree 的组合下会打印一行警告。
它不会阻止你——这是你的机器、你的决定——但会把话说在前面。
