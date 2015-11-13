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
if IS_PYPY or six.PY3:  # pragma: no cover
    OBJECT_INIT = six.get_unbound_function(object.__init__)
else:  # pragma: no cover
    OBJECT_INIT = None


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


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
        return '<%s scope=%s>' % (self.__class__.__name__, self.scope)

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


class DependencyRegistry(object):
    def __init__(self, registry):
        self._registry = registry
        self._map = collections.defaultdict(set)

    def add(self, obj, *keys):
        for k in keys:
            self._map[obj].add(k)

    def missing(self, obj):
        deps = self.get(obj)
        if not deps:
            return
        return itertools.ifilterfalse(self._registry.has, deps)

    def get(self, obj, default=None):
        return self._map.get(obj, default)


class Scope(collections.MutableMapping):
    register = False
    name = None

    instances = None
    instances_factory = dict

    def __init__(self, *args, **kwargs):
        if self.instances is None:
            self.instances = self.instances_factory()
        self.update(dict(*args, **kwargs))

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
        return self.instances[key]

    def __setitem__(self, key, value):
        key = self._key_factory(key)
        self.instances[key] = value

    def __delitem__(self, key):
        key = self._key_factory(key)
        del self.instances[key]

    def __iter__(self):
        return iter(self.instances)

    def __len__(self):
        return len(self.instances)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, dict(self))


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


class NamespacedChildScope(ProxyScope):
    def __init__(self, name, *args, **kwargs):
        self.namespace = name
        super(NamespacedChildScope, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return self.namespace

    def __key_transform__(self, key):
        return '%s__%s' % (self.namespace, key)


class ScopeRegistry(object):
    def __init__(self):
        self._factories = {}
        self._build()

    def _build(self):
        classes = Scope.__subclasses__()
        classes = filter(lambda x: x.register, classes)
        list(map(self.register_factory, classes))

    def register_factory(self, factory, name=None):
        if name is None:
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
            raise KeyError("Scope %s is not known" % scope)

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


class Di(collections.MutableMapping):
    # Scope = Scope
    NamedScope = NamedScope

    _sentinel = object()

    def __init__(self):
        self._providers = ProviderRegistry()
        self._depends = DependencyRegistry(self._providers)
        self._scopes = ScopeRegistry()

    ''' MutableMapping interface '''

    def __contains__(self, item):
        return item in self._providers

    def __getitem__(self, item):
        return self._providers[item]

    def __setitem__(self, key, value):
        self._providers[key] = value

    def __delitem__(self, key):
        del self._providers[key]

    def __iter__(self):
        return iter(self._providers)

    def __len__(self):
        return len(self._providers)

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
        elif isinstance(key_or_keys, list):
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
di.add_instance('di', di)
