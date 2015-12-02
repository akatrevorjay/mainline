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


class IFactoryProvider(IProvider):
    def __init__(self, factory=None):
        self.set_factory(factory)

    def set_factory(self, factory):
        self.factory = factory

    def has_factory(self):
        return bool(self.factory)

    def provide(self, *args, **kwargs):
        return self.factory(*args, **kwargs)

    def has_instance(self):
        return False


class SingletonProvider(IFactoryProvider):
    name = 'singleton'

    def provide(self, *args, **kwargs):
        if not self.has_instance():
            instance = super(SingletonProvider, self).provide(*args, **kwargs)
            self.set_instance(instance)
        return self.instance

    def reset(self):
        if self.has_instance():
            delattr(self, 'instance')

    def has_instance(self):
        return hasattr(self, 'instance')

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
        if self.has_instance():
            return self.scope[self.key]
        instance = super(ScopeProvider, self).provide(*args, **kwargs)
        self.set_instance(instance)
        return instance

    def has_instance(self):
        return self.key in self.scope

    def set_instance(self, instance):
        self.scope[self.key] = instance
