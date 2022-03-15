import contextlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
from types import ModuleType
from typing import Any, Callable, Optional, Sequence, Union
import sys


ModuleFn = Callable[[ModuleType], Any]


@contextlib.contextmanager
def importhook(callback: ModuleFn):
    finder = _Finder(callback)
    sys.meta_path.insert(0, finder)

    try:
        yield
    finally:
        sys.meta_path.reverse()
        sys.meta_path.remove(finder)
        sys.meta_path.reverse()


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, callback):
        self.callback = callback
        self.resolving = []

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[Union[str, bytes]]],
        target: Optional[ModuleType],
    ) -> Optional[importlib.machinery.ModuleSpec]:

        if self.resolving and self.resolving[-1] == fullname:
            return None

        self.resolving.append(fullname)
        try:
            spec = importlib.util.find_spec(fullname)
            if not spec:
                return None
            if spec.loader:
                spec.loader = _Loader(spec.loader, self.callback)
            return spec
        finally:
            self.resolving.pop()


class _Loader(importlib.abc.Loader):
    def __init__(self, loader, callback):
        self.loader = loader
        self.callback = callback

    def load_module(self, fullname: str) -> ModuleType:
        module = self.loader.load_module(fullname)
        if module is not None:
            self.callback(module)
        return module
