# 故障对照表

表里的第一档现象都是**实测遇到过的**，不是假想。

## spawn 阶段

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 状态 `blocked`，错误提示 `agent_not_ready` | agent 起来了但卡在首启弹窗 | `peek` 看是什么弹窗，**交给用户决定**，不要替它选 |
| codex 显示 "Hooks need review" | 它发现 herdr 的状态上报钩子是新的/变过 | `ask` 档交用户答一次；`yolo` 档已带 `--dangerously-bypass-hook-trust`，不会再出现 |
| codex 显示 "Update available" | 版本更新提示挡在前面 | **任何自主档都绕不过**（实测 yolo 下照样弹）。`answer --role X 2` 选 Skip |
| yolo 档下仍然弹窗 | 权限开关只管权限；更新/登录/目录信任不归它管 | `peek` 看清楚，`answer` 回应，再 `watch` |
| `! kind=xxx 没有 yolo 档开关` | 该 CLI 没有对应参数（opencode、qodercli） | 它会照常弹自己的框，只能 `answer`；或换一个支持的 kind |
| `找不到可用 kind` | PATH 上没有那个 agent 的 CLI | `doctor` 看实际可用列表，换一个 kind |
| `pane split 没有返回 pane_id` | herdr 版本或布局异常 | `herdr status` 看客户端/服务端版本是否一致 |

弹窗类问题有个共性：**都只需要用户答一次**。第一次编排前，
建议先手工把每个要用的 agent 在 herdr 里起一次、把弹窗清掉，之后就顺了。

## dispatch 阶段

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `投递后 12 秒内没观察到 working` | 任务卡很可能被启动画面吞了 | 先 `peek`：输入框空着就是没进去，`dispatch --force --role X` 重投 |
| `等不到可交互状态（ready_timeout）` | agent 一直没进入可输入状态 | `peek` 看它在干嘛；可能在登录、在下载、或者卡在别的界面 |
| `agent_blocked` | 投递时对方正停在审批框 | 读出对话框内容给用户，用户答完再 `--force` |
| 任务卡不存在 | 忘了写卡 | `orch.py card --role X --file -` |

**重投前必须先看屏幕。** 超时和停滞都不能证明消息没送到——
如果它其实收到了、正在慢慢干，重投会让同一个任务被执行两遍，
在可写角色身上就是两次改动叠加。

## watch 阶段

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `timeout` 且全程没观察到 working | 多半压根没投进去 | 按 dispatch 那一节处理 |
| `timeout` 但观察到过 working | 活比想象的重，或者它在等人回答 | `peek` 看当前画面；确实需要更久就加大 `--timeout` 重新 `watch` |
| `blocked` | 弹出了审批/提问界面 | `ask` 档读出来交给用户；`auto`/`yolo` 档 watch 已抓屏，读完 `answer` 再 `watch` |
| `failed`：agent 已消失且没有结果文件 | 窗格被关，或 agent 进程崩了 | 看 `logs/<角色>.log`；需要的话重新 `spawn` 这个角色 |
| 结果文件一直不出现 | 卡里没说清产出，或它在终端里长篇输出 | 改卡，强调结果必须写进文件，然后 `--force` 重投 |
| 刚投完卡立刻判成 `done` | 看见的是**上一轮**留下的 `out/<角色>.md` | 投卡前归档旧结果卡；判据加"文件新于本轮任务卡"（`multi-round.md`） |
| 角色已 `timeout`，再 `watch` 立刻返回 | `timeout` 是终态，`watch` 只轮询 `dispatched` | 把 manifest 里该角色的 `state` 改回 `dispatched` 再 `watch`；长任务建议自己轮询 |

## 多轮改派

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `dispatch` 说"没有可投递的角色" | 角色状态是 `done`，不在可投递集合里 | manifest 里 `state` 改回 `spawned` 再投（`multi-round.md`） |
| 子 agent 空转一轮、什么都没做 | 它连不上自家 API（屏幕上有连接/证书错误） | **对同一会话重投**保住上下文，不要新起 agent；先确认网络本身是通的 |
| 想接着用的 agent 窗格已经关了 | 会话还在磁盘上，只是没有窗格 | 用各家的恢复参数起回来（droid：`--resume <id>`，id 在 `~/.factory/sessions/*.jsonl`） |
| 子 agent 推理强度自己变低了 | droid 在 Auto 模式下会自行降档 | 投卡前 `peek` 状态栏确认；要固定就提醒用户手动切回 |

## 结果不对劲

| 现象 | 处置 |
| --- | --- |
| 结果卡缺小节 | 子 agent 没完全遵守协议。可接受就接受，不行就改卡重派 |
| 结果卡说 `## 阻塞` | 它按协议主动停了。读它的问题，补充信息后重投 |
| 只读角色改了文件 | 只读是约定不是沙箱。核对改动，必要时回滚；下次用 `worktree` |
| 内容像是胡编的 | 让另一个 kind 的 reviewer 复核，别自己替它兜底 |

## 环境与版本

| 现象 | 处置 |
| --- | --- |
| `不在 herdr 窗格里（HERDR_ENV≠1）` | 这个工具只能由 herdr 管理的 agent 运行，直接告诉用户 |
| `找不到 herdr 可执行文件` | 检查 PATH 和 `HERDR_BIN_PATH` |
| `herdr 返回的不是 JSON` | 该命令返回的是屏幕文本（`pane read` / `agent read` 就是这样），用 `call_raw` 不要用 `call` |
| 客户端和服务端版本不一致 | `herdr status` 确认。**缺个方法不等于可以去重启用户的 server** |
| 中文输出变乱码 | Windows 控制台代码页问题；`orch.py` 已锁 UTF-8，手工敲 herdr 命令时可能还会遇到 |

## 清理

| 现象 | 处置 |
| --- | --- |
| `keep-pane` 且带错误信息 | 关不掉就留着，不要升级手段去强关 |
| 想保留现场排查 | `cleanup --keep-panes` |
| worktree 的改动还没合并 | 默认就是保留的。别加 `--remove-worktrees` |
| 误关了用户的窗格 | 不会发生：cleanup 只认 manifest 里登记过的 ID。真出了这种事是 bug，报上来 |
