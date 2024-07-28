import copy
import inspect
from functools import wraps
from typing import Any, Dict, List, Optional


class Call:
    def __init__(self, method: str, args: Optional[List[str]] = None, kwargs: Optional[Dict[str, Any]] = None) -> None:
        self.method = method
        self.args = args if args else []
        self.kwargs = kwargs if kwargs else {}


class DIConf:
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
    def __init__(self, conf: DIConf, param: inspect.Parameter) -> None:
        self.conf = conf
        self.param = param


class Container:
    def __init__(self, config: Dict[str, DIConf]) -> None:
        self.config = config

    def _build_dependency(self, param: DIParam):
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
            getattr(dependency, call.method)(*call.args, **call.kwargs)

        if param.conf.cache and not param.conf.cached:
            param.conf.cached = dependency

        return dependency

    def _get_params_to_resolve(self, fun, args=None, kwargs=None) -> List[inspect.Parameter]:
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

    def use_container(self, fun):
        @wraps(fun)
        def wrapped(*args, **kwargs):
            to_resolve = self._get_params_to_resolve(fun, args, kwargs)
            params_to_resolve = self._get_configurable(to_resolve)
            cached = self._get_cached(params_to_resolve)
            resolved = {
                p.param.name: self._build_dependency(p) for p in params_to_resolve if p.param.name not in cached
            }
            return fun(*args, **kwargs | resolved | cached)

        return wrapped

    def _get_configurable(self, parameters: List[inspect.Parameter]) -> List[DIParam]:
        return [DIParam(conf, param) for param in parameters if (conf := self.config.get(param.annotation.__name__))]

    def _get_cached(self, params: List[DIParam]) -> List[DIParam]:
        return {p.param.name: p.conf.cached for p in params if p.conf.cache and p.conf.cached}
