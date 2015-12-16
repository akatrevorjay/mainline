import os
import threading
import collections

from mainline.utils import ProxyMutableMapping


class IScope(ProxyMutableMapping):
    register = False
    name = None

    instances = None
    instances_factory = dict

    def __init__(self, *args, **kwargs):
        if self.instances is None:
            self.instances = self.instances_factory()
        super(IScope, self).__init__(self.instances)
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

    def __contains__(self, key):
        key = self._key_factory(key)
        return super(IScope, self).__contains__(key)

    def __getitem__(self, key):
        key = self._key_factory(key)
        return super(IScope, self).__getitem__(key)

    def __setitem__(self, key, value):
        key = self._key_factory(key)
        super(IScope, self).__setitem__(key, value)

    def __delitem__(self, key):
        key = self._key_factory(key)
        super(IScope, self).__delitem__(key)


class NoneScope(IScope):
    register = True
    name = 'none'

    def __setitem__(self, key, value):
        return


class GlobalScope(IScope):
    register = True
    name = 'global'


class SingletonScope(GlobalScope):
    """ Alias for GlobalScope
    """


class ProcessScope(IScope):
    register = True
    name = 'process'

    def __key_transform__(self, key):
        return '%s_%s' % (os.getpid(), key)


class ThreadScope(IScope):
    register = True
    name = 'thread'

    def __init__(self, *args, **kwargs):
        self._thread_local = threading.local()
        super(ThreadScope, self).__init__(*args, **kwargs)

    def instances_factory(self):
        if not hasattr(self._thread_local, 'instances'):
            self._thread_local.instances = dict()
        return self._thread_local.instances


class ProxyScope(IScope):
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


SCOPE_FACTORIES = {}


class ScopeRegistry(ProxyMutableMapping):
    _factories = SCOPE_FACTORIES

    def __init__(self):
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
            instance = scope_or_scope_factory
            return instance

        elif self.is_scope_factory(scope_or_scope_factory):
            factory = scope_or_scope_factory
            if not instantiate_factory:
                return factory
            instance = factory()
            return instance

        elif scope_or_scope_factory in self._factories:
            factory = self._factories[scope_or_scope_factory]
            return self.resolve(factory)

        else:
            raise KeyError("Scope %s is not known" % scope_or_scope_factory)

    _scope_type = collections.MutableMapping

    @classmethod
    def is_scope_factory(cls, obj):
        return callable(obj) and issubclass(obj, cls._scope_type)

    @classmethod
    def is_scope_instance(cls, obj):
        return isinstance(obj, cls._scope_type)

    @classmethod
    def is_scope(cls, obj):
        return cls.is_scope_factory(obj) or cls.is_scope_instance(obj)
