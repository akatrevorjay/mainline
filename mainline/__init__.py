from mainline._version import __version__
from mainline.catalog import Catalog, ScopeProviderDecorator
from mainline.exceptions import DiError, UnresolvableError
from mainline.injection import ClassPropertyInjector, AutoSpecInjector, SpecInjector
from mainline.provider import ScopeProvider
from mainline.scope import ScopeRegistry

import collections
import functools
import logging

__all__ = ['__version__', 'Di']

_LOG = logging.getLogger(__name__)

_sentinel = object()


class Di(object):
    Catalog = Catalog

    DiError = DiError
    UnresolvableError = UnresolvableError

    scopes = ScopeRegistry()

    _providers_factory = dict
    _dependencies_factory = staticmethod(lambda: collections.defaultdict(set))

    def __init__(self, providers=None, dependencies=None, scopes=None):
        if providers is None:
            providers = self._providers_factory()
        self._providers = providers

        if dependencies is None:
            dependencies = self._dependencies_factory()
        self._dependencies = dependencies

        if scopes:
            self.scopes = scopes

    def update(self, di_or_catalog, providers=True, scopes=True, dependencies=True):
        '''
        Updates this di instance using another Di instance or Catalog.

        :param di_or_catalog: Di or Catalog
        :type di_or_catalog: Di or Catalog
        :param providers: If True update our providers from given source
        :type providers:  bool
        :param scopes: If True update our scopes from given source
        :type scopes: bool
        :param dependencies: If True update our dependencies from given source
        :type dependencies: bool
        '''
        if providers:
            self._providers.update(di_or_catalog.providers)
        if isinstance(di_or_catalog, Di):
            if scopes and scopes is not self.scopes:
                self.scopes.update(di_or_catalog.scopes)
            if dependencies:
                self._dependencies.update(di_or_catalog._dependencies)

    def set_instance(self, key, instance, default_scope='singleton'):
        '''
        Sets instance under specified provider key. If a provider for specified key does not exist, one is created without a provider using the given default_scope.

        :param key: Provider key
        :type key: object
        :param instance: Instance
        :type instance: object
        :param default_scope: Scope key, factory, or instance
        :type default_scope: object or callable
        '''
        if key not in self._providers:
            # We don't know how to create this kind of instance at this time, so add it without a factory.
            factory = None
            self.register_factory(key, factory, default_scope)
        self._providers[key].set_instance(instance)

    def get_provider(self, key):
        '''
        Returns provider for key.

        :param key: Provider key
        :type key: object
        :return: Provider
        :rtype: mainline.provider.IProvider
        '''
        return self._providers[key]

    def get_deps(self, obj):
        '''
        Returns dependencies for key.

        :param key: Provider key
        :type key: object
        :return: Dependencies
        :rtype: set
        '''
        return self._dependencies[obj]

    def get_missing_deps(self, obj):
        '''
        Returns missing dependencies for provider key.

        Missing means if no instance is available and no factory is available.

        :param key: Provider key
        :type key: object
        :return: Missing dependencies
        :rtype: list
        '''
        deps = self.get_deps(obj)
        ret = []
        for key in deps:
            provider = None
            try:
                provider = self.get_provider(key)
            except KeyError:
                pass

            if provider and (provider.has_instance()
                             or provider.has_factory()):
                continue

            ret.append(key)
        return ret

    def iresolve(self, *keys):
        '''
        Iterates over resolved instances for given provider keys.

        :param keys: Provider keys
        :type keys: tuple
        :return: Iterator of resolved instances
        :rtype: generator
        '''
        for key in keys:
            missing = self.get_missing_deps(key)
            if missing:
                raise UnresolvableError("Missing dependencies for %s: %s" % (key, missing))

            try:
                provider = self.get_provider(key)
            except KeyError:
                raise UnresolvableError("Provider does not exist for %s" % key)
            yield provider()

    def resolve(self, *keys):
        '''
        Returns resolved instances for given provider keys.

        If only one positional argument is given, only one is returned.

        :param keys: Provider keys
        :type keys: tuple
        :return: Resolved instance(s); if only one key given, otherwise list of them.
        :rtype: object or list
        '''
        instances = list(self.iresolve(*keys))
        if len(keys) == 1:
            return instances[0]
        return instances

    def resolve_deps(self, obj):
        '''
        Returns list of resolved dependencies for given obj.

        :param obj: Object to lookup dependencies for
        :type obj: object
        :return: Resolved dependencies
        :rtype: list
        '''
        deps = self.get_deps(obj)
        return list(self.iresolve(*deps))

    ''' Decorators '''

    def provider(self, scope='singleton'):
        '''
        Decorator that returns a provider instance using the wrapped as the factory and the specified scope.

        :param scope: Scope key, factory, or instance
        :type scope: object or callable
        :return: decorator
        :rtype: decorator
        '''
        scope = self.scopes.resolve(scope)
        return ScopeProviderDecorator(scope)

    def register_factory(self, key, factory=_sentinel, scope='singleton'):
        '''
        Decorator that registers the wrapped as a provider factory with the specified key and scope.

        :param key: Provider key
        :type key:  object
        :param factory: Factory callable
        :type factory: callable
        :param scope: Scope key, factory, or instance
        :type scope: object or callable
        :return: decorator
        :rtype: decorator
        '''
        if factory is _sentinel:
            return functools.partial(self.register_factory, key, scope=scope)
        if key in self._providers:
            raise KeyError("Key %s already exists" % key)
        scope = self.scopes.resolve(scope)
        provider = ScopeProvider(scope, factory)
        self._providers[key] = provider
        return factory

    def depends_on(self, *keys):
        '''
        Decorator that marks the wrapped as depending on specified provider keys.

        :param keys: Provider keys to mark as dependencies for wrapped
        :type keys: tuple
        :return: decorator
        :rtype: decorator
        '''

        def decorator(wrapped):
            if keys:
                self._dependencies[wrapped].update(keys)
            return wrapped

        return decorator

    def inject_classproperty(self, key, name=None, replace_on_access=False):
        '''
        Decorator that injects the specified key as a classproperty.

        If replace_on_access is True, then it replaces itself with the instance on first lookup.

        :param key: Provider key
        :type key: object
        :param name: Name of classproperty, defaults to key
        :type name: str
        :param replace_on_access: If True, replace the classproperty with the actual value on first lookup
        :type replace_on_access: bool
        '''
        return ClassPropertyInjector(self, key, name=name, replace_on_access=replace_on_access)

    def inject(self, *args, **kwargs):
        '''
        Decorator that injects the specified arguments when the wrapped is called. Argspec is modified on the wrapped accordingly.

        Positional arguments are injected in the order they are given.

        Keyword arguments are injected with the given key name, eg omg='whoa' would inject as omg=<whoa instance>.

        Any specified provider keys are added as dependencies for the wrapped.

        :param keys: Provider keys to inject as positional arguments
        :type keys: tuple
        :param kwargs: Mapping of keyword argument name to provider keys to inject as keyword arguments
        :type kwargs: dict
        :return: decorator
        :rtype: decorator
        '''
        return SpecInjector(self, *args, **kwargs)

    def auto_inject(self, *args, **kwargs):
        '''
        Decorator that magically inspects the argspec of the wrapped upon call, injecting provider instances as names match. It's recommended to use inject() where possible and not this heap of black magic.

        Positional arguments are added as dependencies to wrapped.

        Keyword arguments are handled similarly to inject(), being a mapping of keyword argument name to provider key.

        Any specified provider keys are added as dependencies for the wrapped.

        If dependencies are associated with the wrapped, only those are checked for match in the argspec.

        :param keys: Provider keys to inject as positional arguments
        :type keys: tuple
        :param kwargs: Mapping of keyword argument name to provider keys to inject as keyword arguments
        :type kwargs: dict
        :return: decorator
        :rtype: decorator
        '''
        return AutoSpecInjector(self, *args, **kwargs)
