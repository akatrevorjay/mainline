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


class DiCatalogMeta(type):
    def __new__(mcs, class_name, bases, attributes):
        # providers = {}
        #
        # for base in bases:
        #     if not isinstance(base, DiCatalog):
        #         continue
        #     providers.update(base.providers)
        #
        # providers.update({k: v for k, v in six.iteritems(attributes)
        #                   if isinstance(v, Provider)})

        cls = type.__new__(mcs, class_name, bases, attributes)

        providers = {k: v for k, v in six.iteritems(attributes)
                     if isinstance(v, Provider)}
        cls.providers = providers

        cls.attrs = attributes
        cls.bases = bases
        cls.name = class_name

        return cls


@six.add_metaclass(DiCatalogMeta)
class DiCatalog(object):
    di = None

    def __init__(self, di):
        pass


class Di(ProxyMutableMapping):
    # Scope = Scope
    NamedScope = NamedScope

    _sentinel = object()

    def __init__(self):
        self._providers = ProviderRegistry()
        super(Di, self).__init__(self._providers)
        self._depends = DependencyRegistry(self._providers)
        self._scopes = ScopeRegistry()

        self.Catalog.di = self

    class Catalog(DiCatalog):
        pass

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

    def auto_inject(self, *args, **kwargs):
        return AutoInjector(self, *args, **kwargs)


class Injection(object):
    def __init__(self, injectable):
        self.injectable = injectable

    def __call__(self):
        raise NotImplementedError


class ArgInjection(Injection):
    pass


class NamedInjection(Injection):
    def __init__(self, name, injectable):
        self.name = name
        super(Injection, self).__init__(injectable)


class KwargInjection(NamedInjection):
    pass


class ClassPropertyInjection(NamedInjection):
    pass


class ArgProvider(Provider):
    def __init__(self, value):
        self.value = value

    def provide(self, *args, **kwargs):
        return self.value


class AutoInjector(object):
    def __init__(self, di, *args, **kwargs):
        self.di = di
        self.args = args
        self.kwargs = kwargs

    def __call__(self, wrapped):
        if not any([self.args, self.kwargs]):
            deps = self.di._depends.get(wrapped)
            if not deps:
                deps = self.di.keys()
        else:
            deps = []
            if self.args:
                deps.extend(self.args)
            if self.kwargs:
                deps.extend(self.kwargs.values())
            self.di._depends.add(wrapped, *deps)

        # Remove the number of args from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)

        class Arg(object):
            def __init__(self, key):
                self.key = key

        all_args = []
        new_args = []
        for index, arg in enumerate(spec.args):
            if arg in self.kwargs and self.kwargs[arg] in deps:
                arg = Arg(self.kwargs.pop(arg))
            elif arg in deps:
                arg = Arg(arg)
            else:
                new_args.append(arg)
            all_args.append(arg)

        # Update argspec
        spec = inspect.ArgSpec(new_args, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, args, kwargs):
            args_cur_index = 0
            injected_args = []
            for arg in all_args:
                if isinstance(arg, Arg):
                    obj = self.di.resolve(arg.key)
                    injected_args.append(obj)
                else:
                    injected_args.append(args[args_cur_index])
                    args_cur_index += 1

            remaining_args = args[args_cur_index:]
            if remaining_args:
                injected_args.extend(remaining_args)

            injected_kwargs = {k: self.di.resolve(v) for k, v in six.iteritems(self.kwargs)}
            if kwargs:
                injected_kwargs.update(kwargs)
            return wrapped(*injected_args, **injected_kwargs)

        return wrapper(wrapped)


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
            injected_kwargs = {k: self.di.resolve(v) for k, v in six.iteritems(self.kwargs)}

            if args:
                injected_args.extend(args)
            if kwargs:
                injected_kwargs.update(kwargs)

            return wrapped(*injected_args, **injected_kwargs)

        return wrapper(wrapped)

