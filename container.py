import copy
import inspect
import asyncio
from functools import wraps
from typing import Any, Dict, List, Optional

"""Minimal dependency-injection container.

This module provides a small DI container that can inject dependencies into
functions based on their type annotations.

Key concepts:
- `DIConf`: describes how to build a dependency (constructor args/kwargs, post
  construction attribute assignment, lifecycle calls, caching).
- `Container.use_container`: decorator that injects dependencies into a function
  when it is called.
- `Container.inject`: inject-and-call convenience for sync code.
- `Container.ainject`: inject-and-call convenience for async code.
"""


class Call:
    """A lifecycle call to execute on a constructed dependency.

    Attributes:
        method: Method name to call on the created instance.
        args: Positional arguments for the call.
        kwargs: Keyword arguments for the call.
    """

    def __init__(self, method: str, args: Optional[List[str]] = None, kwargs: Optional[Dict[str, Any]] = None) -> None:
        self.method = method
        self.args = args if args else []
        self.kwargs = kwargs if kwargs else {}


class DIConf:
    """Configuration describing how to build a dependency.

    Attributes:
        cls_: Class (or callable) used to create the dependency.
        args/kwargs: Extra arguments passed to `cls_` when instantiating.
        calls: Lifecycle calls executed after instantiation.
        attrs: Attribute assignments applied after instantiation.
        cache: If True, cache the built instance.
        cached: Stores cached instance once built.
    """

    __slots__ = ("cls_", "name", "args", "kwargs", "calls", "attrs", "cache", "cached")

    def __init__(
        self,
        cls_: Any,
        args: Optional[List[str]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        calls: Optional[List[Call]] = None,
        attrs: Optional[Dict[str, Any]] = None,
        cache: Optional[bool] = False,
    ) -> None:
        self.cls_ = cls_
        self.args = args if args else []
        self.kwargs = kwargs if kwargs else {}
        self.calls = calls if calls else []
        self.attrs = attrs if attrs else {}
        self.cache = cache
        self.cached = None


class DIParam:
    """Pair of (`DIConf`, function parameter) used during resolution."""

    def __init__(self, conf: DIConf, param: inspect.Parameter) -> None:
        self.conf = conf
        self.param = param


class Container:
    """Dependency injection container.

    The container resolves dependencies by matching a parameter's type
    annotation name (`param.annotation.__name__`) against keys in `config`.
    """

    def __init__(self, config: Dict[str, DIConf]) -> None:
        self.config = config

    # Public API

    def use_container(self, fun):
        """Decorator that injects configured dependencies into `fun`.

        - If `fun` is a coroutine function, an async wrapper is returned.
        - Otherwise a sync wrapper is returned.

        Any parameters already supplied via `args`/`kwargs` are not injected.
        """

        if inspect.iscoroutinefunction(fun):

            @wraps(fun)
            async def wrapped(*args, **kwargs):
                return await self.ainject(fun, *args, **kwargs)

            return wrapped
        else:

            @wraps(fun)
            def wrapped(*args, **kwargs):
                return self.inject(fun, *args, **kwargs)

            return wrapped

    def inject(self, fun, *args, **kwargs):
        """Call `fun` with dependencies injected (sync).

        Notes:
        - If `fun` returns an awaitable, it is executed best-effort:
          - if no running loop exists: awaited via `asyncio.run`
          - if a loop is running: scheduled via `loop.create_task` and the
            Task is returned.
        - If you want strict awaiting semantics, prefer `await ainject(...)`.
        """

        to_resolve = self._get_params_to_resolve(fun, args, kwargs)
        params_to_resolve = self._get_configurable(to_resolve)
        cached = self._get_cached(params_to_resolve)
        resolved = {p.param.name: self._build_dependency(p) for p in params_to_resolve if p.param.name not in cached}

        return fun(*args, **kwargs | resolved | cached)

    async def ainject(self, fun, *args, **kwargs):
        """Call `fun` with dependencies injected (async).

        Works with both sync and async callables.
        - If `fun` is sync, its return value is returned.
        - If `fun` returns an awaitable, it is awaited.
        """

        to_resolve = self._get_params_to_resolve(fun, args, kwargs)
        params_to_resolve = self._get_configurable(to_resolve)
        cached = self._get_cached(params_to_resolve)
        resolved = {
            p.param.name: await self._abuild_dependency(p) for p in params_to_resolve if p.param.name not in cached
        }
        return await fun(*args, **kwargs | resolved | cached)

    # Private helpers

    def _build_dependency(self, param: DIParam):
        """Build a dependency synchronously.

        If any configured lifecycle call returns an awaitable, it will be executed
        in a best-effort way:
        - if already inside a running event loop, the awaitable is scheduled and
          not awaited (fire-and-forget)
        - otherwise it is awaited by running a new event loop.
        """

        to_resolve = self._get_params_to_resolve(fun=param.conf.cls_.__init__)
        params_to_resolve = self._get_configurable(to_resolve)
        cached = self._get_cached(params_to_resolve)

        resolved = {}
        if params_to_resolve:
            resolved = {
                p.param.name: self._build_dependency(p) for p in params_to_resolve if p.param.name not in cached
            }

        dependency = param.conf.cls_(*param.conf.args, **resolved | cached | param.conf.kwargs)

        for attr, value in param.conf.attrs.items():
            setattr(dependency, attr, value)

        for call in param.conf.calls:
            result = getattr(dependency, call.method)(*call.args, **call.kwargs)
            if inspect.isawaitable(result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(result)
                else:
                    # BUG: Can be not ready at the time when wrapped function in executed
                    loop.create_task(result)

        if param.conf.cache and not param.conf.cached:
            param.conf.cached = dependency

        return dependency

    async def _abuild_dependency(self, param: DIParam):
        """Async version of `_build_dependency` that awaits async lifecycle calls."""

        to_resolve = self._get_params_to_resolve(fun=param.conf.cls_.__init__)
        params_to_resolve = self._get_configurable(to_resolve)
        cached = self._get_cached(params_to_resolve)

        resolved = {}
        if params_to_resolve:
            resolved = {
                p.param.name: await self._abuild_dependency(p) for p in params_to_resolve if p.param.name not in cached
            }

        dependency = param.conf.cls_(*param.conf.args, **resolved | cached | param.conf.kwargs)

        for attr, value in param.conf.attrs.items():
            setattr(dependency, attr, value)

        for call in param.conf.calls:
            result = getattr(dependency, call.method)(*call.args, **call.kwargs)
            if inspect.isawaitable(result):
                await result

        if param.conf.cache and not param.conf.cached:
            param.conf.cached = dependency

        return dependency

    def _get_params_to_resolve(self, fun, args=None, kwargs=None) -> List[inspect.Parameter]:
        """Return parameters of `fun` that still need resolution.

        Parameters already provided positionally via `args` or explicitly via
        `kwargs` are removed from the returned list.
        """

        args_ = list(copy.deepcopy(args)) if args else []
        kwargs_ = copy.deepcopy(kwargs) if kwargs else {}

        signature = inspect.signature(fun)
        params_ = {k: v for k, v in signature.parameters.items()}

        for param in signature.parameters.keys():
            if args_:
                args_.pop(0)
                params_.pop(param)
            elif kwargs_:
                if param in kwargs_:
                    kwargs_.pop(param)
                    params_.pop(param)

        return list(params_.values())

    def _get_configurable(self, parameters: List[inspect.Parameter]) -> List[DIParam]:
        """Filter parameters to those that have DI configuration."""
        return [DIParam(conf, param) for param in parameters if (conf := self.config.get(param.annotation.__name__))]

    def _get_cached(self, params: List[DIParam]) -> List[DIParam]:
        """Return cached dependencies for the given params."""
        return {p.param.name: p.conf.cached for p in params if p.conf.cache and p.conf.cached}
