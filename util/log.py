from enum import Enum
import inspect
from pathlib import Path
from datetime import datetime

class LogLevel(Enum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3
    FATAL = 4

_log_level = LogLevel.DEBUG

def set_log_level(level: LogLevel) -> None:
    global _log_level
    _log_level = level

def log_msg(msg: str, level: LogLevel, **kwargs) -> None:
    if level.value < _log_level.value:
        return

    reset = "\033[0m"
    underline = "\033[4m"
    log_prefix = {
        LogLevel.DEBUG: "\033[0;34mDEBUG" + reset,
        LogLevel.INFO: "\033[0;32mINFO" + reset + " ",
        LogLevel.WARN: "\033[0;33mWARN" + reset + " ",
        LogLevel.ERROR: "\033[0;31mERROR" + reset,
        LogLevel.FATAL: "\033[0;37m\033[41mFATAL" + reset,
    }

    stack_queue = 1
    if "stack_queue" in kwargs:
        stack_queue = kwargs["stack_queue"]

    # Index 1 refers to the previous frame in the execution stack (the caller)
    caller_frame = inspect.stack()[stack_queue]
    string = "[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] " + \
             log_prefix[level] + " | " + \
             underline + caller_frame.filename + ":" + str(caller_frame.lineno) + reset + " | " + \
             msg

    print(string)

def log_debug(msg: str) -> None:
    log_msg(msg, LogLevel.DEBUG, stack_queue=2)

def log_info(msg: str) -> None:
    log_msg(msg, LogLevel.INFO, stack_queue=2)

def log_warn(msg: str) -> None:
    log_msg(msg, LogLevel.WARN, stack_queue=2)

def log_error(msg: str) -> None:
    log_msg(msg, LogLevel.ERROR, stack_queue=2)

def log_fatal(msg: str) -> None:
    log_msg(msg, LogLevel.FATAL, stack_queue=2)

if __name__ == "__main__":
    log_debug("testing debug")
    log_info("testing info")
    log_warn("testing warning")
    log_error("testing error")
    log_fatal("testing fatal")