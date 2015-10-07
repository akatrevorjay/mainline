from vkproxy.log import get_logger

_LOG = get_logger()

from vkproxy import events, utils
import threading
import functools
import collections
import inspect
import wrapt


class Di(object):
    # scopes are callables that return a scope dictionary
    SCOPE_SINGLETON = lambda self, scopes: scopes['singleton']
    SCOPE_THREAD = lambda self, scopes: self._thread_local.scope[threading.current_thread().ident]
    SCOPE_NONE = lambda self, scopes: None

    def __init__(self):
        self._factories = {}
        self._scoped_instances = collections.defaultdict(dict)
        self._depends_key = collections.defaultdict(set)
        self._depends_obj = collections.defaultdict(set)

    @property
    def _thread_local(self):
        self._thread_local = threading.local()
        self._thread_local.scope = dict()
        return self._thread_local

    def _add_factory(self, key, factory, scope):
        if not callable(factory):
            raise ValueError(factory)
        self._factories[key] = factory, scope
        return factory

    def register(self, key, factory=None, scope=SCOPE_SINGLETON):
        if factory is None:
            return functools.partial(self.register, key, scope=scope)
        return self._add_factory(key, factory, scope)

    def register_instance(self, key, obj):
        # Scope is forced to singleton for instances.
        # We may want to be able to register an instance to a specific scope at some point.
        scope = self.SCOPE_SINGLETON
        factory = lambda: obj
        return self._add_factory(key, factory, scope)

    def has(self, *keys):
        for k in keys:
            if not self.has(k):
                return False
        return True

    def _get_scope(self, scope):
        if callable(scope):
            # s = self.scoped_instances[scope]
            s = self._scoped_instances
            key = scope(self, s)
            if key:
                return s[key]

        # default to fake scope
        return {}

    def resolve(self, key):
        factory, factory_scope = self._factories[key]

        missing_deps = self.missing_depends(key)
        if missing_deps:
            raise Exception("Unresolvable dependencies: %s" % missing_deps)

        scope = self._get_scope(factory_scope)
        if key not in scope:
            scope[key] = factory()

        return scope[key]

    def resolve_many(self, *names):
        return [self.resolve(name) for name in names]

    def depends_on(self, keys, obj=None):
        if obj is None:
            return functools.partial(self.depends_on, keys)
        for k in keys:
            self._depends_key[k].add(obj)
            self._depends_obj[obj].add(k)
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

    def provide_classproperty(self, key, klass=None, name=None, replace_on_access=True):
        if klass is None:
            return functools.partial(self.provide_classproperty, key, name=name,
                                     replace_on_access=replace_on_access)

        if not name:
            name = key

        # Register as dependency for klass
        self.depends_on(key, klass)

        # Add in arguments
        partial = functools.partial(self._wrap_classproperty, klass, key, name, replace_on_access)
        # Create classproperty from it
        clsprop = utils.classproperty(partial)

        # Attach descriptor to object
        setattr(klass, name, clsprop)

        # Return class as this is a decorator
        return klass

    def provide_args(self, wrapped=None, args=None):
        if wrapped is None:
            return functools.partial(self.provide_args,
                                     args=args)

        if args:
            map(self.depends_on, args)
        else:
            args = self._depends_obj[wrapped]

        # HACK Remove the number of arguments from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)
        sargs = spec.args[len(args):]

        # Update argspec
        spec = inspect.ArgSpec(sargs, *spec[1:])
        # spec.__dict__['args'] = sargs

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, wargs, wkwargs):
            injected_args = self.resolve_many(*args)

            def _execute(*_wargs, **_wkwargs):
                if _wargs:
                    injected_args.extend(_wargs)
                return wrapped(*injected_args, **_wkwargs)

            return _execute(*wargs, **wkwargs)

        return wrapper(wrapped)


di = Di()
