#!/usr/bin/env python3
"""herdr-orchestrator 的命令行入口。

这里只做参数解析，命令实现在 orchlib/commands.py，编排逻辑在 orchlib 其余模块。
完整用法见 references/commands.md；先跑 `orch.py doctor` 做环境自检。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 控制台默认不是 UTF-8，不锁死的话中文任务卡和结果会变乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 老 Python 或流已被重定向
        pass

from orchlib import commands, config, herdr, runstore  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(prog="orch.py", description="herdr 多 agent 编排器")
    parser.add_argument("--cwd", default=os.getcwd(), help="项目根目录，默认当前目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="环境自检").set_defaults(func=commands.doctor)

    new = sub.add_parser("new", help="创建 run（只建目录，不启动任何东西）")
    new.add_argument("--role", action="append", required=True,
                     help="角色，格式 名字[:kind[:read-only|write]]，可重复")
    new.add_argument("--task", help="总任务描述文件，- 表示读 stdin")
    new.add_argument("--isolation", default=config.DEFAULT_ISOLATION,
                     choices=list(config.ISOLATION_MODES))
    new.add_argument("--autonomy", default=config.DEFAULT_AUTONOMY,
                     choices=list(config.AUTONOMY_LEVELS),
                     help="ask=保留原生审批；auto=放行审批但留沙箱；yolo=全绕过")
    new.add_argument("--yolo", action="store_true", help="等价于 --autonomy yolo")
    new.set_defaults(func=commands.new)

    card = sub.add_parser("card", help="写任务卡并自动附加交付协议")
    card.add_argument("--role", required=True)
    card.add_argument("--file", required=True, help="任务卡正文，- 表示读 stdin")
    card.add_argument("--run")
    card.set_defaults(func=commands.card)

    spawn = sub.add_parser("spawn", help="建窗格并启动 agent")
    spawn.add_argument("--role", action="append")
    spawn.add_argument("--run")
    spawn.add_argument("--trust-repository", action="store_true",
                       help="仅 worktree 模式：用户已确认仓库可信时才加")
    spawn.set_defaults(func=commands.spawn)

    disp = sub.add_parser("dispatch", help="投递任务卡（非阻塞）")
    disp.add_argument("--role", action="append")
    disp.add_argument("--run")
    disp.add_argument("--force", action="store_true", help="对已投递/超时/阻塞的角色重投")
    disp.set_defaults(func=commands.dispatch_cards)

    wat = sub.add_parser("watch", help="并发等待所有角色落定")
    wat.add_argument("--role", action="append")
    wat.add_argument("--run")
    wat.add_argument("--timeout", type=int, default=config.DEFAULT_WATCH_TIMEOUT_S)
    wat.add_argument("--interval", type=int, default=config.DEFAULT_POLL_INTERVAL_S)
    wat.set_defaults(func=commands.watch_run)

    sta = sub.add_parser("status", help="查看 run 状态")
    sta.add_argument("--run")
    sta.set_defaults(func=commands.status)

    peek = sub.add_parser("peek", help="读回某角色的屏幕内容（仅诊断）")
    peek.add_argument("--role", required=True)
    peek.add_argument("--run")
    peek.add_argument("--lines", type=int, default=config.DEFAULT_PEEK_LINES)
    peek.set_defaults(func=commands.peek)

    ans = sub.add_parser("answer", help="向某角色的交互界面发送按键（先 peek 再决定）")
    ans.add_argument("--role", required=True)
    ans.add_argument("--run")
    ans.add_argument("keys", nargs="+", help="herdr 逻辑键，如 2 enter / esc / ctrl+c")
    ans.set_defaults(func=commands.answer)

    col = sub.add_parser("collect", help="汇总结果为 summary.md")
    col.add_argument("--run")
    col.add_argument("--print-summary", action="store_true", help="同时把全文打到终端")
    col.set_defaults(func=commands.collect)

    cle = sub.add_parser("cleanup", help="只清理本次创建的窗格/tab/workspace")
    cle.add_argument("--run")
    cle.add_argument("--keep-panes", action="store_true")
    cle.add_argument("--remove-worktrees", action="store_true",
                     help="连 worktree 一起删除（会丢掉未合并的改动）")
    cle.set_defaults(func=commands.cleanup)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (runstore.RunError, herdr.HerdrError) as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
