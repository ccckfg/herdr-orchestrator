# 隔离策略

多个 agent 同时改同一棵工作树，**必然互相覆盖**。它们看不见彼此，
各自持有自己那份文件快照，后写的直接盖掉先写的，而且谁都不会报错。

两种隔离模式，`new --isolation` 指定。你自己判断该用哪种；用户有明确要求就听用户的。

## single-writer（默认）

**最多一个 `write` 角色，其余全部只读并行。**

```bash
python "$S" new --role impl:claude:write --role reviewer:codex --role tester:droid
```

- 零冲突：只有一支笔在写。
- 不需要 git，目录不是仓库也能跑。
- 代价：写入不能并行。多个写入任务只能排成多轮。

两个 `write` 角色配 `single-writer` 会被脚本**直接拒绝**，这是有意的——
与其让你以为并行写没问题，不如在建 run 的那一刻就拦住。

**绝大多数情况选这个。** 真正彼此独立、又都要写文件的任务，比想象中少得多。

## worktree

**每个写入角色拿一棵独立的 git worktree 和独立分支。**

```bash
python "$S" new --role api:claude:write --role ui:codex:write --isolation worktree
python "$S" spawn        # 必要时加 --trust-repository
```

- 底层是 `herdr worktree create --branch orch/<run-id>-<角色>`，
  herdr 会把每棵 worktree 挂成一个独立 workspace，agent 住在里面。
- 真并行写入，互不干扰。
- 分支名规则在 `config.py` 的 `WORKTREE_BRANCH_TEMPLATE`。

前提条件：

1. **目录必须是 git 仓库**。`doctor` 会告诉你是不是。
2. **合并由用户做**。编排器不做 merge、不做 rebase、不解冲突——
   那是需要人判断的事。你只负责在 summary 里说清每个分支改了什么。
3. **`--trust-repository` 只在用户确认过仓库可信之后才加**。
   它给的是每请求的 git 信任授权，不是失败后的重试开关。

清理时的默认行为：`cleanup` 只关 workspace（窗口），
**worktree 和分支留在磁盘上**，未合并的改动不会丢。
真要删得加 `--remove-worktrees`，而且必须是用户明确要求。

## 怎么选

```
只有一个角色要写文件？          → single-writer
多个角色要写，但可以排成多轮？  → single-writer，分轮跑
多个角色要写，彼此独立，是 git 仓库，用户接受多分支？ → worktree
多个角色要写，不是 git 仓库？   → single-writer，分轮跑（没有第三条路）
```

## 只读角色也不是绝对安全

"只读"是任务卡里的约束，靠子 agent 自觉，**不是沙箱**。协议里写明了
"除结果文件外不得修改任何文件"，但一个执意要改的 agent 仍然改得了。

所以：

- 交给只读角色的活，就别写成需要改文件才能完成的样子（比如"顺手把格式化一下"）。
- `collect` 之后，如果隔离模式是 `single-writer` 而你怀疑有人越界，
  用 git status 或文件 mtime 自己核一遍——这个脚本不做越界检测。
- 真正需要强隔离的场景，用 `worktree`：那是文件系统层面的分离，不靠自觉。
