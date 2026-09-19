"""编排器自己的异常类型。

单独放一个文件是为了让 roles.py 和 runstore.py 都能用，又不互相 import。
"""


class RunError(Exception):
    """run 定义或状态上的错误，面向用户的中文说明直接放在消息里。"""
