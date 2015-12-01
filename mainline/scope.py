import os
import threading

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

    def __getitem__(self, key):
        key = self._key_factory(key)
        return super(IScope, self).__getitem__(key)

    def __setitem__(self, key, value):
        key = self._key_factory(key)
        super(IScope, self).__setitem__(key, value)

    def __delitem__(self, key):
        key = self._key_factory(key)
        super(IScope, self).__delitem__(key)


class SingletonScope(IScope):
    register = True
    name = 'singleton'


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


class NoneScope(IScope):
    register = True
    name = 'none'

    def __setitem__(self, key, value):
        return


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
