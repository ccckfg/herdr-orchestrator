# modelselect.md：用户的选型偏好

用户用**自然语言**写的一份文档，说明什么活该派给哪个 agent、用哪个模型、什么强度。
脚本不解析它，**由你（编排器）读懂并翻译成参数**——写法自由才是重点。

## 什么时候读

每次编排开工前，`doctor` 之后、`new` 之前。它决定你给每个角色挑哪个 kind 和哪个模型。

```bash
python "$S" doctor          # 「模型偏好」那行会告诉你找没找到
```

查找顺序：

1. `<项目>/.herdr-orch/modelselect.md`（项目级，优先）
2. `~/.herdr-orch/modelselect.md`（用户级）

## 没有这份文档怎么办

**提醒用户写一份，别自己瞎猜模型名。** 猜错了 agent 会在启动时报错，白等一轮。

提醒的时候给个具体的样子，比空口说"请配置一下"有用得多：

```markdown
# 我的选型偏好

- 复杂任务（架构、重构、难 bug）：droid 的 kimi-k3，推理强度 max
- 简单任务（改字符串、加注释、跑测试）：droid 的 glm-5.3-flash
- 要快的：agy 的 gemini-3.8-flash，effort high
- 代码审查：一律用 codex，别用写代码那个模型审自己
- 别用 opencode，我没配 provider
```

用户没写之前，就按角色库的默认 kind 优先级走，并在汇总里说明"用的是默认选型"。

## 怎么把自然语言落成参数

读懂之后，用 `--role-args` 把参数挂到角色上。值按 shell 规则切分，
原样跟在自主档参数后面传给那个 agent 自己的 CLI：

```bash
python "$S" new \
  --role reviewer:codex \
  --role impl:droid:write \
  --role-args reviewer="--model gpt-5.6-sol" \
  --role-args impl="--settings .herdr-orch/<run-id>/droid-impl.json"
```

各家的参数（实测自 2026-09-19 的 `--help`，换版本前核一遍）：

| kind | 选模型 | 推理强度 |
| --- | --- | --- |
| claude | `--model <名>` | 无独立参数 |
| codex | `-m` / `--model <名>` | 用 `-c key=value` 覆盖配置 |
| agy | `--model <名>` | `--effort low\|medium\|high` |
| opencode | `-m provider/model` | 无独立参数 |
| droid | **交互模式没有这个参数**，见下 | 同左 |

## droid 的坑

`droid --model` 不存在——只有 `droid exec -m` 有，而那是非交互模式，不能当 herdr 里的
常驻 agent 用。交互模式选模型有两条路：

1. **生成一份临时设置文件**，用 `--settings` 传进去（它只对本进程生效）。**实测可用**：
   模型和推理强度两个键都会生效，droid 状态栏会变成对应的名字。

   ```json
   { "sessionDefaultSettings": { "model": "glm-5.3-flash", "reasoningEffort": "low" } }
   ```

   写进 run 目录或任意位置，然后：

   ```bash
   --role-args impl='--settings "D:\Project N2\proj\.herdr-orch\droid-impl.json"'
   ```

   模型 ID 用用户 `~/.factory/settings.json` 里 `modelFavorites` 出现过的那些，别自己编。

2. **启动后在会话里切**：`answer` 发 `/model` 再选。能用但脆——菜单顺序会变，
   不推荐在自动流程里用。

### 路径里有空格一定要加引号

`--role-args` 的值会被切分成参数。路径带空格时**必须在值里面用引号括住路径**
（上面那行 `'--settings "D:\...\x.json"'` 就是），否则会被切成两个参数。
反斜杠不用转义，脚本已经关掉了转义处理。带空格的路径实测能正常传到 droid。

保险起见：`spawn` 之后 `peek` 一眼，droid 状态栏会显示当前模型，确认切过去了再 `dispatch`。

## 便宜模型会给你错答案

一条实测记录，供你判断"简单任务"的边界：同一个任务（统计某目录下 .py 文件数和行数）、
同一个 droid、只换模型：

| 模型 | 答案 | 实际 |
| --- | --- | --- |
| glm-5.3 强度 max | 10 个文件 / 1608 行，逐文件行数全对 | ✅ |
| glm-5.3-flash 强度 low | 1 个文件 / 91 行 | ❌ 实为 13 个 / 1874 行 |

flash 那次根本没递归进子目录，连单个文件的行数都数错了，而且**它报告得非常自信**，
格式规范、有表格有依据——你不核对就看不出来。

所以：**凡是结果要拿来做决定的活，别派给低强度模型**。
"简单任务"指的是那种错了你一眼能看出来的活，不是"看起来简单的活"。

转告用户时可以这么说：

- **按"任务难度"分档比按"角色"分更好用**：同一个 reviewer，审小改动和审架构该用的模型不一样
- **明确说不要用什么**（没配 provider 的、太贵的），比只说要用什么更省事
- **模型 ID 要写准**：droid 的写在 `~/.factory/settings.json` 的 `modelFavorites` 里，
  agy/claude/codex 的可以用各自的 `--help` 或 `/model` 查
- 偏好可以带条件，你读得懂就行：比如"跑测试用最便宜的，反正只是看红绿"
