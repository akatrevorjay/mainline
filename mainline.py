import fang

namespace = '.com.vkspider.vkproxy'

di = fang.Di(namespace=namespace)
providers = di.providers


def create_registry(name):
    name = '%s.%s' % (namespace, name)
    return fang.ResourceProviderRegister(namespace=name)


from vkproxy import events, utils
import functools
import collections


class RegistryError(Exception):
    pass


class DependencyNotFound(RegistryError, KeyError):
    pass


class Registry(dict):
    def __init__(self, *args, **kwargs):
        super(Registry, self).__init__(*args, **kwargs)
        self.on_change = events.Event()
        self.on_key_change = events.EventManager()

        self.depends = collections.defaultdict(set)

        self.update_cls_props = collections.defaultdict(set)
        self.on_change += self._on_change_update_depends_cls_props

    def __setitem__(self, key, value):
        super(Registry, self).__setitem__(key, value)
        self.on_change(key, value)
        self.on_key_change.fire(key, key, value)

    def _on_change_update_depends_cls_props(self, key, value):
        depends_cls_props = self.update_cls_props.get(key, [])
        for d in depends_cls_props:
            setattr(d, key, value)

    def depends_on(self, obj, key):
        self.depends[key].add(key)

    def register(self, callableobj, key):
        self[key] = callableobj

    def register_instance(self, key, obj):
        instancewrap = lambda: obj
        return self.register(instancewrap, key)

    has = dict.has_key

    def resolve(self, name):
        if self.has(name):
            return self[name]()
        else:
            raise DependencyNotFound(name)

    def resolve_many(self, *names):
        return [self.resolve(name) for name in names]

    def resolve_deps(self, key):
        if key not in self.depends:
            return
        deps = self.depends[key]
        return self.resolve_many(*deps)

    def _wrap_classproperty(self, cls, key, property_name, replace_on_access, *args, **kwargs):
        print locals()
        val = registry.resolve(key)
        if replace_on_access:
            setattr(cls, property_name, val)
        return val

    def provide_as_classproperty(self, klass, key, property_name=None, replace_on_access=True, update_on_change=True):
        if not property_name:
            property_name = key

        # Register as dependency for klass
        self.depends_on(klass, key)

        if update_on_change:
            # Allow to update later
            self.update_cls_props[klass].add(key)

        # Add in arguments
        meth = functools.partial(self._wrap_classproperty, klass, key, property_name, replace_on_access)
        # Create classproperty from it
        clsprop = utils.classproperty(meth)

        # Attach descriptor to object
        setattr(klass, key, clsprop)

        # Return class as this is a decorator
        return klass


registry = Registry()
