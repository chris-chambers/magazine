# Originally adapted from IPython's autoreload.py, written by Thomas Heller,
# Pauli Virtanen, and the IPython Development Team; and distributed under the
# BSD License.

from collections import defaultdict
import gc
from inspect import isfunction, isclass, ismethod
from types import FunctionType, MethodType, ModuleType
from typing import Any, Callable, Iterable, Text
import weakref


UpgradeFn = Callable[[Any, Any, Iterable['UpgradeFn']], bool]


def reload(
    module: ModuleType,
    upgraders: Iterable[UpgradeFn] = ...,
 ) -> ModuleType:
    # Import importlib.reload here so that this module can reload itself.
    # If the import is outside this function, it is cleared during reload and
    # can't be resolved.
    from importlib import reload as _reload

    if upgraders is ...:
        upgraders = UPGRADERS

    saved_dict = module.__dict__.copy()
    name = module.__name__
    loader = module.__loader__
    spec = module.__spec__
    magazine_refs = module.__dict__.get(
        '__magazine__', defaultdict(weakref.WeakSet))
    module.__dict__.clear()
    module.__dict__.update(
        __name__=name,
        __loader__=loader,
        __spec__=spec,
        __magazine__=magazine_refs,
    )

    try:
        # Try to reload the module.
        module = _reload(module)
    except:
        # Restore the previous dict on failure.
        module.__dict__.update(saved_dict)
        raise

    for name, obj in saved_dict.items():
        if getattr(obj, '__module__', None) == module.__name__:
            magazine_refs[name].add(obj)

    # Delete the saved module dict so members can potentially be
    # garbage-collected and avoid needless upgrading.
    del saved_dict

    # Upgrade existing upgradeable objects.
    for name, refset in magazine_refs.items():
        for old in refset:
            new = module.__dict__.get(name)
            if old is not None and new is not None:
                # print(f'upgrading {module.__name__}.{name}')
                upgrade(old, new, upgraders)

    return module


def upgrade(old, new, upgraders: Iterable[UpgradeFn]) -> bool:
    return any(upgrade(old, new, upgraders) for upgrade in upgraders)


def upgrade_function(
    old: FunctionType,
    new: FunctionType,
    _: Iterable[UpgradeFn],
 ) -> bool:
    if not isfunction(old) or not isfunction(new):
        return False

    _copyattr(old, new, '__closure__')
    _copyattr(old, new, '__code__')
    _copyattr(old, new, '__defaults__')
    _copyattr(old, new, '__dict__')
    _copyattr(old, new, '__doc__')
    _copyattr(old, new, '__globals__')
    return True


def upgrade_method(
    old: MethodType,
    new: MethodType,
    upgraders: Iterable[UpgradeFn],
 ) -> bool:
    if not ismethod(old) or not ismethod(new):
        return False

    return upgrade_function(old.__func__, new.__func__, upgraders)


def upgrade_class(old: type, new: type, upgraders: Iterable[UpgradeFn]) -> bool:
    if not isclass(old) or not isclass(new):
        return False

    remove = []
    for key in old.__dict__:
        try:
            # In unusual cases, key may not be a string, which will cause
            # `getattr` to throw `TypeError`.  If so, just skip it.
            oldattr = getattr(old, key)
        except TypeError:
            continue

        try:
            newattr = getattr(new, key)
        except AttributeError:
            remove.append(key)
            continue

        if oldattr is newattr:
            continue

        # Try to upgrade the old attr with the new definition.  If upgrading is
        # not possible, just copy the new attr across.
        if not upgrade(oldattr, newattr, upgraders):
            _copyattr(old, new, key)

    for key in remove:
        _delattr(old, key)

    for key in set(new.__dict__) - old.__dict__.keys():
        _copyattr(old, new, key)

    # Update the __class__ of existing instances.
    for ref in gc.get_referrers(old):
        if type(ref) is old:
            ref.__class__ = new

    return True


def upgrade_property(
    old: property,
    new: property,
    upgraders: Iterable[UpgradeFn],
 ) -> bool:
    if not isinstance(old, property) or not isinstance(new, property):
        return False

    upgrade_property_part(old, new, 'fget', 'getter', upgraders)
    upgrade_property_part(old, new, 'fset', 'setter', upgraders)
    upgrade_property_part(old, new, 'fdel', 'deleter', upgraders)
    return True


def upgrade_property_part(
    old: property,
    new: property,
    name: Text,
    mutator: Text,
    upgraders: Iterable[UpgradeFn],
):
    # If the old and new parts are both functions, upgrade the old function,
    # otherwise replace the old function with the new function.  This handles
    # the cases where both old and new have functions, where old has no function
    # or where new has no function.
    oldpart = getattr(old, name)
    newpart = getattr(new, name)
    if isfunction(oldpart) and isfunction(newpart):
        upgrade_function(oldpart, newpart, upgraders)
    else:
        getattr(old, mutator)(newpart)


UPGRADERS = [
    upgrade_class,
    upgrade_function,
    upgrade_property,
    upgrade_method,
]


def _copyattr(dst: Any, src: Any, name: Text):
    try:
        setattr(dst, name, getattr(src, name))
    except (AttributeError, TypeError):
        pass


def _delattr(obj: Any, name: Text):
    try:
        delattr(obj, name)
    except (AttributeError, TypeError):
        pass
