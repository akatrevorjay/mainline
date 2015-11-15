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
import sys

IS_PYPY = '__pypy__' in sys.builtin_module_names
if IS_PYPY or six.PY3:
    OBJECT_INIT = six.get_unbound_function(object.__init__)
else:
    OBJECT_INIT = None


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


class ProxyMutableMapping(collections.MutableMapping):
    def __init__(self, mapping):
        self.__mapping = mapping

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.__mapping)

    def __contains__(self, item):
        return item in self.__mapping

    def __getitem__(self, item):
        return self.__mapping[item]

    def __setitem__(self, key, value):
        self.__mapping[key] = value

    def __delitem__(self, key):
        del self.__mapping[key]

    def __iter__(self):
        return iter(self.__mapping)

    def __len__(self):
        return len(self.__mapping)


class DiError(Exception):
    pass


class UnresolvableError(DiError):
    pass


class Provider(object):
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self.provide(*args, **kwargs)

    def provide(self, *args, **kwargs):
        raise NotImplementedError

    def set_instance(self, instance):
        raise NotImplementedError


class FactoryProvider(Provider):
    def __init__(self, factory):
        self.factory = factory

    def provide(self, *args, **kwargs):
        return self.factory(*args, **kwargs)


class SingletonProvider(FactoryProvider):
    name = 'singleton'

    def provide(self, *args, **kwargs):
        if not hasattr(self, 'instance'):
            instance = super(SingletonProvider, self).provide(*args, **kwargs)
            self.set_instance(instance)
        return self.instance

    def reset(self):
        if hasattr(self, 'instance'):
            delattr(self, 'instance')

    def set_instance(self, instance):
        self.instance = instance


class ScopeProvider(FactoryProvider):
    def __init__(self, scope, factory, key=''):
        self.key = key
        self.scope = scope
        super(ScopeProvider, self).__init__(factory)

    def __repr__(self):
        return '<%s factory=%s scope=%s>' % (self.__class__.__name__,
                                             self.factory,
                                             self.scope)

    def provide(self, *args, **kwargs):
        if self.key in self.scope:
            return self.scope[self.key]
        instance = super(ScopeProvider, self).provide(*args, **kwargs)
        self.set_instance(instance)
        return instance

    def set_instance(self, instance):
        self.scope[self.key] = instance


class ProviderRegistry(dict):
    has = dict.__contains__


class DependencyRegistry(ProxyMutableMapping):
    def __init__(self, registry):
        self._registry = registry
        self._map = collections.defaultdict(set)
        super(DependencyRegistry, self).__init__(self._map)

    def add(self, obj, *keys):
        for k in keys:
            self._map[obj].add(k)

    def missing(self, obj):
        if obj not in self._map:
            return
        deps = self.get(obj)
        if not deps:
            return
        return itertools.ifilterfalse(self._registry.has, deps)


class Scope(ProxyMutableMapping):
    register = False
    name = None

    instances = None
    instances_factory = dict

    def __init__(self, *args, **kwargs):
        if self.instances is None:
            self.instances = self.instances_factory()
        super(Scope, self).__init__(self.instances)
        self.update(dict(*args, **kwargs))

    def __str__(self):
        return self.name

    def __key_transform__(self, key):
        return key

    class _key(str):
        pass

    def _key_factory(self, key):
        if not isinstance(key, self._key):
            key = self.__key_transform__(key)
            key = self._key(key)
        return key

    def __getitem__(self, key):
        key = self._key_factory(key)
        return super(Scope, self).__getitem__(key)

    def __setitem__(self, key, value):
        key = self._key_factory(key)
        super(Scope, self).__setitem__(key, value)

    def __delitem__(self, key):
        key = self._key_factory(key)
        super(Scope, self).__delitem__(key)


class SingletonScope(Scope):
    register = True
    name = 'singleton'


class ProcessScope(Scope):
    register = True
    name = 'process'

    def __key_transform__(self, key):
        return '%s_%s' % (os.getpid(), key)


class ThreadScope(Scope):
    register = True
    name = 'thread'

    def __init__(self, *args, **kwargs):
        self._thread_local = threading.local()
        super(ThreadScope, self).__init__(*args, **kwargs)

    def instances_factory(self):
        if not hasattr(self._thread_local, 'instances'):
            self._thread_local.instances = dict()
        return self._thread_local.instances


class NoneScope(Scope):
    register = True
    name = 'none'

    def __setitem__(self, key, value):
        return


class NamedScope(Scope):
    def __init__(self, name):
        self.name = name


class ProxyScope(Scope):
    def __init__(self, scope, *args, **kwargs):
        self.instances = scope
        super(ProxyScope, self).__init__(*args, **kwargs)


class NamespacedProxyScope(ProxyScope):
    def __init__(self, namespace, scope, *args, **kwargs):
        self.namespace = namespace
        super(NamespacedProxyScope, self).__init__(scope, *args, **kwargs)

    @property
    def name(self):
        return self.namespace

    def __key_transform__(self, key):
        return '%s__%s' % (self.namespace, key)


class ScopeRegistry(ProxyMutableMapping):
    def __init__(self):
        self._factories = {}
        super(ScopeRegistry, self).__init__(self._factories)
        self._build()

    def _build(self):
        classes = Scope.__subclasses__()
        classes = filter(lambda x: x.register, classes)
        list(map(self.register_factory, classes))

    def register_factory(self, factory, name=None):
        if name is None:
            # name = str(factory)
            name = getattr(factory, 'name', None)
        if name:
            self._factories[name] = factory
        self._factories[factory] = factory

    def resolve(self, scope_or_scope_factory):
        if self.is_scope_instance(scope_or_scope_factory):
            scope = scope_or_scope_factory
            return scope
        elif self.is_scope_factory(scope_or_scope_factory):
            factory = scope_or_scope_factory
            return factory()
        elif scope_or_scope_factory in self._factories:
            factory = self._factories[scope_or_scope_factory]
            return self.resolve(factory)
        else:
            raise KeyError("Scope %s is not known" % scope_or_scope_factory)

    _scope_type = Scope

    @classmethod
    def is_scope_factory(cls, obj):
        return callable(obj) and issubclass(obj, cls._scope_type)

    @classmethod
    def is_scope_instance(cls, obj):
        return isinstance(obj, cls._scope_type)

    @classmethod
    def is_scope(cls, obj):
        return cls.is_scope_factory(obj) or cls.is_scope_instance(obj)


class Di(ProxyMutableMapping):
    # Scope = Scope
    NamedScope = NamedScope

    _sentinel = object()

    def __init__(self):
        self._providers = ProviderRegistry()
        super(Di, self).__init__(self._providers)
        self._depends = DependencyRegistry(self._providers)
        self._scopes = ScopeRegistry()

    ''' API '''

    def register_factory(self, key, factory=_sentinel, scope='singleton'):
        if factory is self._sentinel:
            return functools.partial(self.register_factory, key, scope=scope)
        if key in self._providers:
            raise KeyError("Key %s already exists" % key)
        scope = self._scopes.resolve(scope)
        self._providers[key] = ScopeProvider(scope, factory)
        return factory

    def add_instance(self, key, instance, default_scope='singleton'):
        if key not in self._providers:
            # We don't know how to create this kind of instance at this time, so add it without a factory.
            factory = None
            self.register_factory(key, factory, default_scope)
        self._providers[key].set_instance(instance)

    def _coerce_key_or_keys(self, key_or_keys, *more_keys):
        keys = []
        return_list = True

        if more_keys:
            # Multiple arguments given
            keys.append(key_or_keys)
            keys.extend(more_keys)
        elif isinstance(key_or_keys, (list, tuple)):
            # Singular item; treat as an iterable
            keys.extend(key_or_keys)
        else:
            # Singular str
            keys.append(key_or_keys)
            return_list = False

        return keys, return_list

    def depends_on(self, *keys):
        def decorator(method):
            self._depends.add(method, *keys)
            return method

        return decorator

    def get_deps(self, obj):
        return self._depends.get(obj)

    def _resolve_one(self, key):
        provider = self._providers[key]

        # TODO Check the scopes for missing keys, not the registry
        missing = self._depends.missing(key)
        if missing:
            raise UnresolvableError("Missing dependencies for %s: %s" % (key, missing))

        return provider()

    def resolve(self, key_or_keys, *more_keys):
        # only py3k can have default args with *args
        keys, return_list = self._coerce_key_or_keys(key_or_keys, *more_keys)
        ret = list(map(self._resolve_one, keys))

        if return_list:
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

    def inject_classproperty(self, key, klass=None, name=None, replace_on_access=False):
        if klass is None:
            return functools.partial(
                self.inject_classproperty,
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

    def inject(self, *args, **kwargs):
        return Injector(self, *args, **kwargs)


class Injector(object):
    def __init__(self, di, *args, **kwargs):
        self.di = di
        self.args = args
        self.kwargs = kwargs

    def __call__(self, wrapped):
        if not any([self.args, self.kwargs]):
            self.args = self.di._depends.get(wrapped)
        else:
            injections = []
            if self.args:
                injections.extend(self.args)
            if self.kwargs:
                injections.extend(self.kwargs.values())
            self.di._depends.add(wrapped, *injections)

        # Remove the number of args from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)
        new_args = spec.args[len(self.args):]

        # Update argspec
        spec = inspect.ArgSpec(new_args, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, args, kwargs):
            injected_args = self.di.resolve(self.args)
            injected_kwargs = {}
            if self.kwargs:
                injected_kwargs.update(zip(
                    self.kwargs.keys(), self.di.resolve(self.kwargs.values())
                ))

            def _execute(*_args, **_kwargs):
                if _args:
                    injected_args.extend(_args)
                if _kwargs:
                    injected_kwargs.update(_kwargs)
                return wrapped(*injected_args, **injected_kwargs)

            return _execute(*args, **kwargs)

        return wrapper(wrapped)
