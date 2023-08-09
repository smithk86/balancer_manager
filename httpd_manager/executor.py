from concurrent.futures import Executor
from contextvars import ContextVar

executor: ContextVar[Executor | None] = ContextVar("executor", default=None)
