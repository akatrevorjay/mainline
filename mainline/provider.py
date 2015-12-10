import functools

from mainline.exceptions import UnprovidableError
from mainline.scope import ScopeRegistry, NoneScope
_sentinel = object()


class IProvider(object):
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self.provide(*args, **kwargs)

    def provide(self, *args, **kwargs):
        raise NotImplementedError

    def has_instance(self):
        raise NotImplementedError

    def set_instance(self, instance):
        raise NotImplementedError

    @property
    def providable(self):
        raise NotImplementedError


class IFactoryProvider(IProvider):
    def __init__(self, factory=None):
        self.set_factory(factory)

    def set_factory(self, factory):
        self.factory = factory

    def has_factory(self):
        return bool(self.factory)

    def provide(self, *args, **kwargs):
        if not self.providable:
            raise UnprovidableError(self)
        return self.factory(*args, **kwargs)

    def has_instance(self):
        return False

    @property
    def providable(self):
        return self.has_instance() or self.has_factory()


class Provider(IFactoryProvider):
    scopes = ScopeRegistry()

    def __init__(self, factory, scope=NoneScope, key=''):
        self.key = key
        self.scope = self.scopes.resolve(scope)
        super(Provider, self).__init__(factory)

    def __repr__(self):
        return '<%s factory=%s scope=%s>' % (self.__class__.__name__,
                                             self.factory,
                                             self.scope)

    def provide(self, *args, **kwargs):
        if self.has_instance():
            return self.scope[self.key]
        instance = super(Provider, self).provide(*args, **kwargs)
        self.set_instance(instance)
        return instance

    def has_instance(self):
        return self.key in self.scope

    def set_instance(self, instance):
        self.scope[self.key] = instance


def provider_factory(factory=_sentinel, scope=NoneScope):
    '''
    Decorator to create a provider using the given factory, and scope.
    Can also be used in a non-decorator manner.

    :param scope: Scope key, factory, or instance
    :type scope: object or callable
    :return: decorator
    :rtype: decorator
    '''
    if factory is _sentinel:
        return functools.partial(provider_factory, scope=scope)
    provider = Provider(factory, scope)
    return provider
