import collections
import functools
import itertools
import logging

from mainline.exceptions import UnresolvableError
from mainline.catalog import Catalog, ScopeProviderDecorator
from mainline.injection import ClassPropertyInjector, AutoSpecInjector, SpecInjector
from mainline.scope import IScope
from mainline.utils import ProxyMutableMapping

_LOG = logging.getLogger(__name__)


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


class ProviderRegistry(dict):
    has = dict.__contains__


class ScopeRegistry(ProxyMutableMapping):
    def __init__(self):
        self._factories = {}
        super(ScopeRegistry, self).__init__(self._factories)
        self._build()

    def _build(self):
        classes = IScope.__subclasses__()
        classes = filter(lambda x: x.register, classes)
        list(map(self.register_factory, classes))

    def register_factory(self, factory, name=None):
        if name is None:
            # name = str(factory)
            name = getattr(factory, 'name', None)
        if name:
            self._factories[name] = factory
        self._factories[factory] = factory

    def resolve(self, scope_or_scope_factory, instantiate_factory=True):
        if self.is_scope_instance(scope_or_scope_factory):
            scope = scope_or_scope_factory
            return scope
        elif self.is_scope_factory(scope_or_scope_factory):
            factory = scope_or_scope_factory
            if instantiate_factory:
                return factory()
            else:
                return factory
        elif scope_or_scope_factory in self._factories:
            factory = self._factories[scope_or_scope_factory]
            return self.resolve(factory)
        else:
            raise KeyError("Scope %s is not known" % scope_or_scope_factory)

    _scope_type = IScope

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
    _sentinel = object()

    def __init__(self):
        self._providers = ProviderRegistry()
        super(Di, self).__init__(self._providers)
        self._depends = DependencyRegistry(self._providers)
        self._scopes = ScopeRegistry()

    ''' Catalog '''

    Catalog = Catalog

    def update_from_catalog(self, catalog):
        self.update(catalog.get_providers())

    def provider(self, scope='singleton'):
        scope = self._scopes.resolve(scope)
        return ScopeProviderDecorator(scope)

    ''' API '''

    def set_instance(self, key, instance, default_scope='singleton'):
        if key not in self._providers:
            # We don't know how to create this kind of instance at this time, so add it without a factory.
            factory = None
            self.register_factory(key, factory, default_scope)
        self._providers[key].set_instance(instance)

    def get_deps(self, obj):
        return self._depends.get(obj)

    def _resolve_one(self, key):
        provider = self._providers[key]

        # TODO Check the scopes for missing keys, not the registry
        missing = self._depends.missing(key)
        if missing:
            raise UnresolvableError("Missing dependencies for %s: %s" % (key, missing))

        return provider()

    def resolve(self, *keys):
        if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
            keys = keys[0]
            return_list = True
        else:
            return_list = False

        ret = list(map(self._resolve_one, keys))

        if return_list:
            return ret
        else:
            return ret[0]

    def resolve_deps(self, obj, **kwargs):
        deps = self.get_deps(obj)
        return self.resolve(deps, **kwargs)

    ''' Decorators '''

    def register_factory(self, key, factory=_sentinel, scope='singleton'):
        if factory is self._sentinel:
            return functools.partial(self.register_factory, key, scope=scope)
        if self._providers.has(key):
            raise KeyError("Key %s already exists" % key)
        provider = self.provider(scope)(factory)
        self._providers[key] = provider
        return factory

    def depends_on(self, *keys):
        def decorator(method):
            self._depends.add(method, *keys)
            return method

        return decorator

    def inject_classproperty(self, key, name=None, replace_on_access=False):
        return ClassPropertyInjector(self, key, name=name, replace_on_access=replace_on_access)

    def inject(self, *args, **kwargs):
        return SpecInjector(self, *args, **kwargs)

    def auto_inject(self, *args, **kwargs):
        return AutoSpecInjector(self, *args, **kwargs)
