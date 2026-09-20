# orch.py 命令参考

统一写法（`$S` 指向 skill 目录下的 `scripts/orch.py`）：

```bash
S="<skill-dir>/scripts/orch.py"
python "$S" <子命令> [选项]
```

全局选项：

| 选项 | 说明 |
| --- | --- |
| `--cwd PATH` | 项目根目录，默认当前目录。run 目录建在它下面 |
| `--json` | 输出 JSON，供脚本消费；不加则输出给人看的文本 |

多数子命令支持 `--run <run-id>` 指定 run；不指定就用最新的那个。
`--role` 可重复，省略表示"所有角色"。

退出码：`0` 成功；`1` 业务错误（stderr 有中文说明）；`2` 参数错误。

---

## doctor

环境自检，不改任何东西。

```bash
python "$S" doctor
python "$S" doctor --json
```

输出里最重要的是 **可用 kind**：这是扫 PATH 实测出来的，
起 agent 前以它为准，不要照文档猜。

`HERDR_ENV≠1` 时除 `doctor` / `status` / `card` / `collect` 外的命令都会直接拒绝。

## new

创建 run。只建目录和 manifest，不启动任何进程。

```bash
python "$S" new \
  --role reviewer:codex \
  --role tester:droid \
  --role impl:claude:write \
  --task task.md \
  --isolation single-writer
```

| 选项 | 说明 |
| --- | --- |
| `--role 名字[:kind[:模式]]` | 必填，可重复。模式取 `read-only` / `write` |
| `--task FILE` | 总任务描述，`-` 读 stdin。只是留档，不会发给子 agent |
| `--isolation` | `single-writer`（默认）或 `worktree` |
| `--autonomy` | `ask`（默认）/ `auto` / `yolo`，见 `autonomy.md` |
| `--yolo` | `--autonomy yolo` 的简写 |

角色名必须匹配 `[a-z][a-z0-9_-]{0,31}`（herdr 的要求）。
一轮超过 4 个角色、或 `single-writer` 下出现两个 `write` 角色，都会被拒绝。

## card

写任务卡，并自动在卡尾附加交付协议。

```bash
python "$S" card --role reviewer --file card.md
cat card.md | python "$S" card --role reviewer --file -
```

协议里会填入该角色的结果文件绝对路径和可写范围，**不要自己手写这段**。
重复执行会覆盖旧卡，用于二轮改派。

## spawn

给每个角色准备窗格并启动对应 kind 的 agent。

```bash
python "$S" spawn
python "$S" spawn --role reviewer
python "$S" spawn --trust-repository      # 仅 worktree 模式且用户已确认仓库可信
```

行为要点：

- 全程 `--no-focus`，不抢用户焦点。
- 当前 tab 里窗格（含别人开的）加上新起的超过 3 个时，自动改开新 tab，
  否则 agent 的 TUI 会被挤成没法看的窄条。
- `worktree` 模式下，可写角色走 `herdr worktree create`，落在独立 workspace。
- 启动卡在弹窗时状态记 `blocked`，不会失败退出——用 `peek` 看，再按自主档决定谁来回应。
- 非 `ask` 档会把该 kind 的原生绕过参数带上（`-- <args>`）。
  某个 kind 没有对应开关时，输出里会带 `! kind=xxx 没有 yolo 档开关`。

## dispatch

投递任务卡。**不带 `--wait`**，提交完就返回。

```bash
python "$S" dispatch
python "$S" dispatch --role reviewer --force
```

投递前会等到对方 `interactive_ready` 且状态落定，再留一点渲染余量；
投递后会盯 12 秒看有没有进入 `working`，没有就在输出里警告。

`--force` 才会对已投递 / 超时 / 阻塞的角色重投。**重投前先 `peek`**：
超时不等于没投递成功，盲目重投会让任务执行两遍。

**二轮改派**（同一个 agent 接着干下一件活，保住上下文）也走这里：
`card` 覆盖旧卡 → `dispatch --force --role <角色>`。角色状态已是 `done` 时
`dispatch` 会说"没有可投递的角色"，需要先把 manifest 里的 `state` 改回 `spawned`；
投新卡前记得把旧的 `out/<角色>.md` 改名归档，否则等待逻辑会拿它当本轮结果。
完整姿势见 `multi-round.md`。

## watch

并发等待所有角色落定。靠一次 `herdr api snapshot` 拿到全部 agent 状态，
配合结果文件落盘判完成。

```bash
python "$S" watch --timeout 900 --interval 5
python "$S" watch --role reviewer --timeout 300
```

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `--timeout` | 1800 秒 | 整轮上限，不是单个角色的 |
| `--interval` | 5 秒 | 两次快照之间的间隔 |

终态：`done` / `blocked` / `timeout` / `failed`。全部 `done` 时退出码为 0。

## status

查看 run 的当前状态，只读。

```bash
python "$S" status
python "$S" status --run 20260919-203154-6e7b --json
```

## peek

读回某角色的屏幕内容，同时存进 `logs/<角色>.log`。

```bash
python "$S" peek --role reviewer --lines 200
```

**只用于诊断**：判断对方是不是卡在弹窗、任务卡有没有进去。
不要拿屏幕内容当结果——会截断，也会被 TUI 重绘搅乱。

## answer

向某角色的交互界面发送按键，用于回应绕不过的弹窗。

```bash
python "$S" answer --role probe 2            # 选第 2 项
python "$S" answer --role probe 2 enter      # 选完再回车
python "$S" answer --role probe esc          # 退出当前界面
```

键是 herdr 的逻辑键，herdr 会先校验全部按键再写入，不会发一半。

**先 `peek` 再 `answer`**：选项顺序各家不同，盲按会选错。
发送后角色状态会退回被卡住之前那一档（没投过卡的回 `spawned`，投过的回 `dispatched`），
接着重新 `watch` 即可。

`ask` 档下这个动作原则上该由用户做——编排器不替子 agent 答审批框。

## collect

把所有结果卡汇总成 `summary.md`。

```bash
python "$S" collect
python "$S" collect --print-summary     # 同时把全文打到终端
```

汇总里包含角色状态表、需要人工处理的清单、以及每个角色结果卡的全文。

## cleanup

只清理 manifest 里登记过的资源。

```bash
python "$S" cleanup
python "$S" cleanup --keep-panes            # 留着窗格，方便你自己接管看
python "$S" cleanup --remove-worktrees      # 危险：会删掉 worktree 里未合并的改动
```

清理顺序是窗格 → tab → workspace。关不掉的会保留并在输出里说明原因，
不会为了关掉而升级手段。`--remove-worktrees` 必须用户明确要求才加。

**这个项目后面还有活就用 `--keep-panes`**：窗格留着，下一轮直接改卡重投给同一个
agent，它的上下文原封不动。关掉窗格并不销毁会话，但恢复要靠各家 CLI 的
`--resume <会话id>`，麻烦且得提前记下 id（见 `multi-round.md`）。
