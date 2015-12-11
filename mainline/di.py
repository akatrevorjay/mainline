import functools

from mainline.catalog import ICatalog, Catalog
from mainline.exceptions import UnresolvableError
from mainline.injection import ClassPropertyInjector, AutoSpecInjector, SpecInjector
from mainline.scope import ScopeRegistry, NoneScope, GlobalScope
from mainline.provider import Provider, provider_factory

_sentinel = object()


class Di(ICatalog):
    '''
    Dependency injection container.
    '''
    scopes = ScopeRegistry()

    # Hook these in for usability
    provider = staticmethod(provider_factory)
    Catalog = Catalog
    Provider = Provider

    def __init__(self, providers_factory=Catalog, dependencies_factory=dict):
        self._providers = providers_factory()
        self._dependencies = dependencies_factory()
        super(Di, self).__init__()

    @property
    def providers(self):
        '''
        Public attribute for provider mapping
        '''
        return self._providers

    @property
    def dependencies(self):
        '''
        Public attributes for dependency mapping
        '''
        return self._dependencies

    def update(self, catalog=None, dependencies=None, allow_overwrite=False):
        '''
        Convenience method to update this Di instance with the specified contents.

        :param catalog: ICatalog supporting class or mapping
        :type catalog: ICatalog or collections.Mapping
        :param dependencies: Mapping of dependencies
        :type dependencies: collections.Mapping
        :param allow_overwrite: If True, allow overwriting existing keys. Only applies to providers.
        :type allow_overwrite: bool
        '''
        if catalog:
            self._providers.update(catalog, allow_overwrite=allow_overwrite)
        if dependencies:
            self._dependencies.update(dependencies)

    def get_deps(self, obj):
        '''
        Returns dependencies for key.

        :param key: Dependent holder key
        :type key: object
        :return: Dependencies
        :rtype: set
        '''
        return self._dependencies.get(obj, set())

    def get_missing_deps(self, obj):
        '''
        Returns missing dependencies for provider key.
        Missing meaning no instance can be provided at this time.

        :param key: Provider key
        :type key: object
        :return: Missing dependencies
        :rtype: list
        '''
        deps = self.get_deps(obj)
        ret = []
        for key in deps:
            provider = self._providers.get(key)
            if provider and provider.providable:
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

            provider = self._providers.get(key)
            if not provider:
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

    def register_factory(self, key, factory=_sentinel, scope=NoneScope, allow_overwrite=False):
        '''
        Creates and registers a provider using the given key, factory, and scope.
        Can also be used as a decorator.

        :param key: Provider key
        :type key:  object
        :param factory: Factory callable
        :type factory: callable
        :param scope: Scope key, factory, or instance
        :type scope: object or callable
        :return: Factory (or None if we're creating a provider without a factory)
        :rtype: callable or None
        '''
        if factory is _sentinel:
            return functools.partial(self.register_factory, key, scope=scope)
        if not allow_overwrite and key in self._providers:
            raise KeyError("Key %s already exists" % key)
        provider = self.provider(factory, scope)
        self._providers[key] = provider
        return factory

    def set_instance(self, key, instance, default_scope=GlobalScope):
        '''
        Sets instance under specified provider key. If a provider for specified key does not exist, one is created
        without a factory using the given scope.

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
                if wrapped not in self._dependencies:
                    self._dependencies[wrapped] = set()
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
        Decorator that injects the specified arguments when the wrapped is called. Argspec is modified on the wrapped
        accordingly.

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
        Decorator that magically inspects the argspec of the wrapped upon call, injecting provider instances as names
        match. It's recommended to use inject() where possible and not this heap of black magic.

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
