from vkproxy.log import get_logger

_LOG = get_logger()

import threading
import functools
import collections
import inspect
import wrapt
import os
import itertools
import six
import weakref


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


def consume(iterator, n=None):
    "Advance the iterator n-steps ahead. If n is none, consume entirely."
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(itertools.islice(iterator, n, n), None)


class Scope(collections.MutableMapping):
    register_as = None
    instances = None
    instances_factory = dict

    def __init__(self, *args, **kwargs):
        if self.instances is None:
            self.instances = self.instances_factory()
        self.update(dict(*args, **kwargs))

    def __key_transform__(self, key):
        return key

    def __getitem__(self, key):
        key = self.__key_transform__(key)
        return self.instances[key]

    def __setitem__(self, key, value):
        key = self.__key_transform__(key)
        self.instances[key] = value

    def __delitem__(self, key):
        key = self.__key_transform__(key)
        del self.instances[key]

    def __iter__(self):
        return iter(self.instances)

    def __len__(self):
        return len(self.instances)


class SingletonScope(Scope):
    register_as = 'singleton'


class ProcessScope(Scope):
    register_as = 'process'

    def __key_transform__(self, key):
        return '%s_%s' % (os.getpid(), key)


class ThreadScope(Scope):
    register_as = 'thread'

    def __init__(self, *args, **kwargs):
        self._thread_local = threading.local()
        super(ThreadScope, self).__init__(*args, **kwargs)

    def instances_factory(self):
        if not hasattr(self._thread_local, 'instances'):
            self._thread_local.instances = dict()
        return self._thread_local.instances


class NoneScope(Scope):
    register_as = 'none'

    def __setitem__(self, key, value):
        return


class NamedScope(Scope):
    def __init__(self, name):
        self.name = name


class ProxyScope(Scope):
    def __init__(self, scope, *args, **kwargs):
        self.instances = scope
        super(ProxyScope, self).__init__(*args, **kwargs)


class NamespacedChildScope(ProxyScope):
    def __init__(self, name, *args, **kwargs):
        self.namespace = name
        super(NamespacedChildScope, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return self.namespace

    def __key_transform__(self, key):
        return '%s.%s' % (self.namespace, key)


class ScopeRegistry(object):
    def __init__(self, parent):
        self._map = {}
        self._build()

    def _build(self):
        classes = Scope.__subclasses__()
        cls_map = {s.register_as: s for s in classes if s.register_as}
        for name, cls in six.iteritems(cls_map):
            self.register(name, cls)

    def register(self, name, scope_or_scope_factory):
        if callable(scope_or_scope_factory):
            instance = scope_or_scope_factory()
            # Save lookup from factory to instance
            self._map[scope_or_scope_factory] = instance
        else:
            instance = scope_or_scope_factory
        self._map[name] = instance

    def resolve(self, scope):
        if scope not in self._map:
            raise KeyError("Scope %s does not exist" % scope)
        scope = self._map[scope]
        return scope

    def get(self, scope):
        return self.resolve(scope)


class Provider(object):
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self.provide(*args, **kwargs)

    def provide(self, *args, **kwargs):
        raise NotImplementedError


class FactoryProvider(Provider):
    def __init__(self, factory):
        self.factory = factory

    def provide(self, *args, **kwargs):
        return self.factory(*args, **kwargs)


class ScopeProvider(FactoryProvider):
    def __init__(self, scope, key, factory):
        self.key = key
        self.scope = scope
        super(ScopeProvider, self).__init__(factory)

    def __call__(self, *args, **kwargs):
        if self.key in self.scope:
            return self.scope[self.key]
        instance = super(ScopeProvider, self).__call__(*args, **kwargs)
        self.set_instance(instance)
        return instance

    def set_instance(self, instance):
        self.scope[self.key] = instance


class SingletonProvider(FactoryProvider):
    def __call__(self, *args, **kwargs):
        if not hasattr(self, 'instance'):
            self.instance = super(SingletonProvider, self).__call__(*args, **kwargs)
        return self.instance


class Registry(object):
    def __init__(self, parent):
        self._parent = parent

        self._map = {}

    def has(self, key):
        return key in self._map

    __contains__ = has

    _sentinel = object()

    def get(self, key, default=None):
        value = self._map.get(key, default)
        if value is self._sentinel:
            raise KeyError(key)
        return value

    def __getitem__(self, key):
        return self.get(key, default=self._sentinel)

    def add(self, key, scope, factory):
        if key in self:
            raise KeyError("Key %s already exists" % key)
        provider = ScopeProvider(scope, key, factory)
        self._map[key] = provider
        return provider

    def remove(self, key):
        del self._map[key]

    __delitem__ = remove

    def discard(self, key):
        if self.has(key):
            self.remove(key)


class DependencyRegistry(object):
    def __init__(self, parent):
        self._registry = parent._registry

        self._map = collections.defaultdict(set)

    def add(self, obj, *keys):
        # if obj not in self._lookup:
        #     self._lookup[obj] = set()

        for k in keys:
            self._map[obj].add(k)

    def missing(self, obj):
        deps = self.get(obj)
        if not deps:
            return
        return itertools.ifilterfalse(self._registry.has, deps)

    def get(self, obj, default=None):
        # if obj not in self._lookup:
        #     return
        return self._map.get(obj, default)


class DiError(Exception):
    pass


class UnresolvableError(DiError):
    pass


class Di(object):
    def __init__(self):
        self._scopes = ScopeRegistry(self)
        self._registry = Registry(self)
        self._depends = DependencyRegistry(self)

    # Scope = Scope
    NamedScope = NamedScope

    _sentinel = object()

    def register_factory(self, key, factory=_sentinel, scope='singleton'):
        if factory is self._sentinel:
            return functools.partial(self.register_factory, key, scope=scope)
        scope = self._scopes.get(scope)
        self._registry.add(key, scope, factory)
        return factory

    def register_instance(self, key, instance, default_scope='singleton'):
        if not self._registry.has(key):
            # We don't know how to create this kind of instance at this time, so add it without a factory.
            factory = None
            self.register_factory(key, factory, default_scope)
        self._registry[key].set_instance(instance)

    def _coerce_key_or_keys(self, key_or_keys, *more_keys):
        keys = []

        if more_keys:
            # Multiple arguments given
            keys.append(key_or_keys)
            keys.extend(more_keys)
        elif isinstance(key_or_keys, six.string_types):
            # Singular str
            keys.append(key_or_keys)
        else:
            # Singular item; treat as an iterable
            keys.extend(key_or_keys)

        return keys

    def depends_on(self, key_or_keys, obj=None):
        if obj is None:
            return functools.partial(self.depends_on, keys_or_keys)
        keys = self._coerce_key_or_keys(key_or_keys)
        self._depends.add(obj, *keys)
        return obj

    def get_deps(self, obj):
        return self._depends.get(obj)

    def _resolve_one(self, key):
        provider = self._registry[key]

        # TODO Check the scopes for missing keys, not the registry
        missing = self._depends.missing(key)
        if missing:
            raise UnresolvableError("Missing dependencies for %s: %s" % (key, missing))

        return provider()

    def resolve(self, key_or_keys, *more_keys):
        # only py3k can have default args with *args
        keys = self._coerce_key_or_keys(key_or_keys, *more_keys)
        ret = list(map(self._resolve_one, keys))

        if not isinstance(key_or_keys, six.string_types) or more_keys:
            # Always return a sequence when given multiple arguments
            return ret
        else:
            return ret[0]

    def resolve_deps(self, obj, **kwargs):
        deps = self.get_deps(obj)
        return self.resolve(deps, **kwargs)

    def _wrap_classproperty(self, cls, key, name, replace_on_access, owner=None):
        # owner is set to the instance if applicable
        val = self.resolve(key)
        if replace_on_access:
            setattr(cls, name, val)
        return val

    def provide_classproperty(self, key, klass=None, name=None, replace_on_access=False):
        if klass is None:
            return functools.partial(
                self.provide_classproperty,
                key, name=name,
                replace_on_access=replace_on_access,
            )

        if not name:
            name = key

        # Register as dependency for klass
        self._depends.add(klass, key)

        # Add in arguments
        partial = functools.partial(self._wrap_classproperty, klass, key, name, replace_on_access)
        # Create classproperty from it
        clsprop = classproperty(partial)

        # Attach descriptor to object
        setattr(klass, name, clsprop)

        # Return class as this is a decorator
        return klass

    def provide_partial(self, wrapped=None, args=None):
        if wrapped is None:
            return functools.partial(self.provide_partial, args=args)

        if args:
            self._depends.add(wrapped, *args)
        else:
            args = self._depends.get(wrapped)

        injected_args = self.resolve(args)
        return functools.partial(wrapped, *injected_args)

    def provide_args(self, wrapped=None, args=None):
        if wrapped is None:
            return functools.partial(self.provide_args, args=args)

        if args:
            self._depends.add(wrapped, *args)
        else:
            args = self._depends.get(wrapped)

        # HACK Remove the number of arguments from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)
        sargs = spec.args[len(args):]

        # Update argspec
        spec = inspect.ArgSpec(sargs, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, wargs, wkwargs):
            injected_args = self.resolve(args)

            def _execute(*_wargs, **_wkwargs):
                if _wargs:
                    injected_args.extend(_wargs)
                return wrapped(*injected_args, **_wkwargs)

            return _execute(*wargs, **wkwargs)

        return wrapper(wrapped)


di = Di()
di.register_instance('di', di)
