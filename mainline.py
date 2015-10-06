from vkproxy.log import get_logger

_LOG = get_logger()

from vkproxy import events, utils
import threading
import functools
import collections
import inspect
import decorator
import wrapt


# scopes are callables that return the partitioning key
SCOPE_SINGLETON = lambda: 'singleton'
# TODO This should really go in thread local so it's removed with the thread
SCOPE_THREAD = lambda: 'thread_%s' % threading.current_thread().ident
SCOPE_NONE = lambda: None


class Di(object):
    SCOPE_SINGLETON = SCOPE_SINGLETON
    SCOPE_THREAD = SCOPE_THREAD
    SCOPE_NONE = SCOPE_NONE

    Factory = collections.namedtuple('Factory', ['factory', 'scope'])

    def __init__(self, *args, **kwargs):
        self._factories = {}
        self._scoped_instances = collections.defaultdict(lambda: collections.defaultdict(dict))
        self._depends_key = collections.defaultdict(set)
        self._depends_obj = collections.defaultdict(set)

        self.on_change = events.Event()
        self.on_key_change = events.EventManager()

        self._update_cls_props = collections.defaultdict(set)
        self.on_change += self._on_change_update_depends_cls_props

    def _on_change_update_depends_cls_props(self, key, value):
        for klass, property_name in self._update_cls_props.get(key, []):
            setattr(klass, property_name, value)

    def _add_factory(self, key, factory, scope):
        if not callable(factory):
            raise ValueError(factory)

        self._factories[key] = self.Factory(factory, scope)

        self.on_change(key, factory)
        self.on_key_change.fire(key, key, factory)
        return factory

    def register(self, key, factory=None, scope=SCOPE_SINGLETON):
        if factory is None:
            return functools.partial(self.register, key, scope=scope)
        return self._add_factory(key, factory, scope)

    def register_instance(self, key, obj, scope=SCOPE_SINGLETON):
        factory = lambda: obj
        return self._add_factory(key, factory, scope)

    def has_many(self, *keys):
        for k in keys:
            if not self.has(k):
                return False
        return True

    has = has_many

    def _get_scope(self, scope):
        if callable(scope):
            # s = self.scoped_instances[scope]
            s = self._scoped_instances

            key = scope()
            if key:
                return s[key]

        # default to fake scope
        return {}

    def resolve(self, key):
        f = self._factories[key]

        missing_deps = self.missing_depends(key)
        if missing_deps:
            raise Exception("Unresolvable dependencies: %s" % missing_deps)

        scope = self._get_scope(f.scope)
        if key not in scope:
            scope[key] = f.factory()

        return scope[key]

    def resolve_many(self, *names):
        return [self.resolve(name) for name in names]

    def depends_on(self, key, obj=None):
        if obj is None:
            return functools.partial(self.depends_on, key)
        self._depends_key[key].add(obj)
        self._depends_obj[obj].add(key)
        return obj

    def missing_depends(self, obj):
        if obj not in self._depends_obj:
            return
        deps = self._depends_obj[obj]
        fltr = lambda x: not self.has(x)
        keys = filter(fltr, deps)
        return keys

    def resolve_deps(self, obj):
        if obj not in self._depends_obj:
            return
        deps = self._depends_obj[obj]
        return self.resolve_many(*deps)

    def _wrap_classproperty(self, cls, key, name, replace_on_access, owner=None):
        # owner is set to the instance if applicable
        val = self.resolve(key)
        if replace_on_access:
            setattr(cls, name, val)
        return val

    def provide_classproperty(self, key, klass=None, name=None, replace_on_access=True, update_on_change=False):
        if klass is None:
            return functools.partial(self.provide_classproperty, key, name=name,
                                     replace_on_access=replace_on_access, update_on_change=update_on_change)

        if not name:
            name = key

        # Register as dependency for klass
        self.depends_on(key, klass)

        if update_on_change:
            # Allow to update later
            self._update_cls_props[key].add((klass, name))

        # Add in arguments
        partial = functools.partial(self._wrap_classproperty, klass, key, name, replace_on_access)
        # Create classproperty from it
        clsprop = utils.classproperty(partial)

        # Attach descriptor to object
        setattr(klass, name, clsprop)

        # Return class as this is a decorator
        return klass

    def provide_args(self, wrapped=None, names=None):
        if wrapped is None:
            return functools.partial(self.provide_args,
                                     names=names)

        if names:
            for n in names:
                self.depends_on(n, wrapped)
        else:
            names = self._depends_obj[wrapped]

        # HACK Remove the number of arguments from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)
        args = spec.args[len(names):]
        # spec.__dict__['args'] = spec.args[len(names):]
        spec = inspect.ArgSpec(args, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, args, kwargs):
            injected_args = self.resolve_deps(wrapped)
            # injected_args = self.resolve_many(*names)

            def _execute(*_args, **_kwargs):
                if _args:
                    injected_args.extend(_args)
                return wrapped(*injected_args, **_kwargs)

            return _execute(*args, **kwargs)

        return wrapper(wrapped)


di = Di()
