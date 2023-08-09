from collections.abc import Callable, Coroutine

from httpd_manager.base import Cluster
from httpd_manager.httpx import HttpxBalancerManager

EnableAllRoutesHandler = Callable[[HttpxBalancerManager, Cluster], Coroutine[None, None, None]]
