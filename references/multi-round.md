# 多轮复用：让子 agent 带着上下文继续

一个模块做完第一轮，第二轮别新起 agent。子 agent 会话里攒着它读过的代码、踩过的坑、
自己定下的取舍——重起一个等于把这些全扔掉，让它从零重读一遍代码，既慢又贵，
还容易做出和上一轮不一致的决定。

**默认做法：同一个模块的后续任务，永远投给同一个 agent。**

## 三种续接方式，按优先级选

### 1. 窗格还活着 → 改卡 + 强制重投（最省）

```bash
python "$S" card --role tui --file round2.md      # 覆盖旧卡
python "$S" dispatch --force --role tui           # 投给还活着的那个 agent
```

`dispatch` 只对 `dispatched` 状态的角色生效，角色已经 `done` 时会提示"没有可投递的角色"。
把 manifest 里该角色的 `state` 改回 `spawned` 再投：

```bash
python - <<'EOF'
import json, glob
p = sorted(glob.glob("<项目>/.herdr-orch/*/manifest.json"))[-1]
m = json.load(open(p, encoding="utf-8"))
for r in m["roles"]:
    r["state"] = "spawned"; r["error"] = None; r["finished_at"] = None
m["state"] = "dispatched"
json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
```

**投新卡前先把旧结果卡改名归档**（例如 `out/tui.md` → `out/tui-round1.md`）。
否则你的等待逻辑会看见上一轮的文件，立刻误报"完成"——这个坑很容易踩，
因为文件大小稳定、内容看着也像真的。

### 2. 窗格已关 → 用 agent 自己的会话 id 恢复

窗格关了不等于会话没了。各家 CLI 都能按会话 id 恢复，起的时候带上即可：

```bash
--role-args tui='--settings "<绝对路径>.json" --resume 47461685-58ed-4625-921b-c3e31818872d'
```

droid 的会话文件在 `~/.factory/sessions/<id>.jsonl`，按 cwd 和修改时间能认出是哪个：

```bash
ls -t ~/.factory/sessions/*.jsonl | head        # 最近的在前
head -c 400 ~/.factory/sessions/<id>.jsonl      # 头部有 cwd
```

**开工时就把会话 id 记下来**（写进 run 目录下一个自己的小文件，或项目记忆），
别等窗格关了再去翻。恢复后屏幕上会留着上一轮的尾巴，那是会话真的回来了的证据。

### 3. 实在要新起 → 在卡里把上一轮的结论喂回去

只有"上一轮的 agent 彻底不可用"时才走这条。新卡里要写明：上一轮做了什么、
产出在哪、哪些结论已经定死不要推翻。相当于手工重建上下文，比前两种差得多。

## 收尾时留着窗格

```bash
python "$S" cleanup --keep-panes
```

只要这个项目后面还有活，就别关窗格。`collect` 出的 summary 照常生成，
窗格留着，下一轮直接走方式 1。

## 复用时的几个坑

- **会话越长越容易被降档**：droid 在 Auto 模式下会自己把推理强度从 Max 降到 High/Low；
  投卡前 `peek` 一眼状态栏确认，必要时提醒用户手动切回。
- **会话过长会触发压缩**：屏幕出现 `Compressing history...` 属正常，等它压完继续。
- **上游抖动不要重起会话**：某些 CLI 会偶发连不上自家 API（droid 实测会在屏幕上打
  `Unable to establish a secure connection to ...`，这一轮什么都不做就空转结束）。
  处置是**对同一会话重投一次**，不是新起 agent——上下文还在，重投即可。
- **别拿 MCP 指示器当健康判据**：那些 MCP 服务器和子 agent 写代码没关系。
  真判据是投卡后它能不能进入 `working`。

## 等待逻辑要跟着调整

多轮之后，"结果文件存在且大小稳定"不再够用——上一轮的文件就在那儿。
判完成时加一条：**文件修改时间必须新于本轮任务卡**。

```bash
[ -s "$OUT" ] && [ "$OUT" -nt "$CARD" ] && echo "本轮真的完成了"
```

`watch --timeout` 到期会把角色标成终态 `timeout`，之后再 `watch` 会立刻返回、不再轮询。
长任务要么给足超时，要么自己轮询（`herdr agent list` + 上面那条文件判据），
最后再跑一次 `watch` 让 manifest 落到 `done`。
