class IProvider(object):
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self.provide(*args, **kwargs)

    def provide(self, *args, **kwargs):
        raise NotImplementedError

    def set_instance(self, instance):
        raise NotImplementedError


class IFactoryProvider(IProvider):
    def __init__(self, factory=None):
        self.set_factory(factory)

    def set_factory(self, factory):
        self.factory = factory

    def has_factory(self):
        return bool(self.factory)

    def provide(self, *args, **kwargs):
        return self.factory(*args, **kwargs)


class SingletonProvider(IFactoryProvider):
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


class ScopeProvider(IFactoryProvider):
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
