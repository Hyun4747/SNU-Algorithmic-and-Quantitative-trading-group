"""
This file is a utility module that provides a wrapper around the line_profiler module
for profiling Python code. The purpose of this module is to allow users to profile
their code using the line_profiler module if it is available, and fallback to a no-op
function if it is not available.
"""

import builtins
from typing import Callable, ParamSpec, TypeVar

try:
    from line_profiler import LineProfiler  # type: ignore
except ImportError:
    pass
from loguru import logger

T = TypeVar("T")
P = ParamSpec("P")


if not hasattr(builtins, "profile"):

    def no_op(func: Callable[P, T]) -> Callable[P, T]:
        return func

    profile = no_op
else:
    logger.warning("Using kernprof for profiling. This will slow down the execution.")
    original_profile = getattr(builtins, "profile")

    def profile(func: Callable[P, T]) -> Callable[P, T]:
        return original_profile(func)

    # prevent using builtins.profile directly without importing
    del builtins.profile  # type: ignore
