from vkproxy.log import get_logger

_LOG = get_logger()

from vkproxy import events, utils
import threading
import functools
import collections
import inspect
import decorator
import wrapt


# scopes are callables that return the partitioning key
SCOPE_SINGLETON = lambda: 'singleton'
# TODO This should really go in thread local so it's removed with the thread
SCOPE_THREAD = lambda: 'thread_%s' % threading.current_thread().ident
SCOPE_NONE = lambda: None


class Di(object):
    SCOPE_SINGLETON = SCOPE_SINGLETON
    SCOPE_THREAD = SCOPE_THREAD
    SCOPE_NONE = SCOPE_NONE

    Factory = collections.namedtuple('Factory', ['factory', 'scope'])

    def __init__(self, *args, **kwargs):
        self._factories = {}
        self._scoped_instances = collections.defaultdict(lambda: collections.defaultdict(dict))
        self._depends_key = collections.defaultdict(set)
        self._depends_obj = collections.defaultdict(set)

        self.on_change = events.Event()
        self.on_key_change = events.EventManager()

        self._update_cls_props = collections.defaultdict(set)
        self.on_change += self._on_change_update_depends_cls_props

    def _on_change_update_depends_cls_props(self, key, value):
        for klass, property_name in self._update_cls_props.get(key, []):
            setattr(klass, property_name, value)

    def _add_factory(self, key, factory, scope):
        if not callable(factory):
            raise ValueError(factory)

        self._factories[key] = self.Factory(factory, scope)

        self.on_change(key, factory)
        self.on_key_change.fire(key, key, factory)
        return factory

    def register(self, key, factory=None, scope=SCOPE_SINGLETON):
        if factory is None:
            return functools.partial(self.register, key, scope=scope)
        return self._add_factory(key, factory, scope)

    def register_instance(self, key, obj, scope=SCOPE_SINGLETON):
        factory = lambda: obj
        return self._add_factory(key, factory, scope)

    def has(self, key):
        return key in self._factories

    def has_many(self, *keys):
        for k in keys:
            if not self.has(k):
                return False
        return True

    def _get_scope(self, scope):
        if callable(scope):
            # s = self.scoped_instances[scope]
            s = self._scoped_instances

            key = scope()
            if key:
                return s[key]

        # default to fake scope
        return {}

    def resolve(self, key):
        f = self._factories[key]

        missing_deps = self.missing_depends_for(key)
        if missing_deps:
            raise Exception("Unresolvable dependencies: %s" % missing_deps)

        scope = self._get_scope(f.scope)
        if key not in scope:
            scope[key] = f.factory()

        return scope[key]

    def resolve_many(self, *names):
        return [self.resolve(name) for name in names]

    def depends_on(self, key, obj=None):
        if obj is None:
            return functools.partial(self.depends_on, key)
        self._depends_key[key].add(obj)
        self._depends_obj[obj].add(key)
        return obj

    def missing_depends_for(self, obj):
        if obj not in self._depends_obj:
            return
        deps = self._depends_obj[obj]
        fltr = lambda x: not self.has(x)
        keys = filter(fltr, deps)
        return keys

    def resolve_deps(self, obj):
        if obj not in self._depends_obj:
            return
        deps = self._depends_obj[obj]
        return self.resolve_many(*deps)

    def _wrap_classproperty(self, cls, key, name, replace_on_access, owner=None):
        # owner is set to the instance if applicable
        val = self.resolve(key)
        if replace_on_access:
            setattr(cls, name, val)
        return val

    def provide_classproperty(self, key, klass=None, name=None, replace_on_access=True, update_on_change=False):
        if klass is None:
            return functools.partial(self.provide_classproperty, key, name=name,
                                     replace_on_access=replace_on_access, update_on_change=update_on_change)

        if not name:
            name = key

        # Register as dependency for klass
        self.depends_on(key, klass)

        if update_on_change:
            # Allow to update later
            self._update_cls_props[key].add((klass, name))

        # Add in arguments
        partial = functools.partial(self._wrap_classproperty, klass, key, name, replace_on_access)
        # Create classproperty from it
        clsprop = utils.classproperty(partial)

        # Attach descriptor to object
        setattr(klass, name, clsprop)

        # Return class as this is a decorator
        return klass

    def provide_args(self, keys, func=None):
        if func is None:
            return functools.partial(self.provide_args, keys)
        vals = self.resolve_many(*keys)
        partial = functools.partial(func, *vals)
        # partial = functools.update_wrapper(partial, func)
        partial = functools.wraps(func)(partial)
        return partial

    def provide_argspec(self, func=None, keys=None):
        if func is None:
            return functools.partial(self.provide_argspec)

        if not keys:
            spec = inspect.getargspec(func)
            keys = filter(self.has, spec.args)

        kwargs = {k: self.resolve(k) for k in keys}
        partial = functools.partial(func, **kwargs)
        return functools.wraps(func)(partial)

    def provide_argspec_lazy_orig(self, func=None, keys=None):
        if func is None:
            return functools.partial(self.provide_argspec_lazy_orig, keys=keys)

        spec = inspect.getargspec(func)
        # keys = ['arg1']

        def wrapped(keys, *args, **kwargs):
            if not keys:
                keys = filter(self.has, spec.args)

            injected_kwargs = {k: self.resolve(k) for k in keys}
            partial = functools.partial(func, **injected_kwargs)
            # partial = functools.wraps(func)(partial)
            return partial(*args, **kwargs)

        wrapped = functools.partial(wrapped, keys)
        # wrapped = functools.wraps(func)(wrapped)
        return wrapped

    def provide_argspec_lazy(self, wrapped=None, names=None):
        _LOG.debug('wrapped=%s names=%s', wrapped, names)

        if wrapped is None:
            return functools.partial(self.provide_argspec_lazy,
                                     names=names)

        if names:
            for n in names:
                self.depends_on(n, wrapped)
        else:
            names = self._depends_obj[wrapped]

        # HACK Remove the number of arguments from the wrapped function's argspec
        spec = inspect.getargspec(wrapped)
        args = spec.args[len(names):]
        # spec.__dict__['args'] = spec.args[len(names):]
        spec = inspect.ArgSpec(args, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def wrapper(wrapped, instance, args, kwargs):
            _LOG.debug('args=%s kwargs=%s', args, kwargs)
            # injected_args = self.resolve_deps(wrapped)
            injected_args = self.resolve_many(*names)

            def _execute(*_args, **_kwargs):
                if _args:
                    injected_args.extend(_args)
                _LOG.debug('_args=%s _kwargs=%s injected_args=%s', _args, _kwargs, injected_args)
                return wrapped(*injected_args, **_kwargs)

            return _execute(*args, **kwargs)

        return wrapper(wrapped)


di = Di()


def omg(arg1, default=True, nil=None, *args, **kwargs):
    print 'omg', arg1, default, nil, args, kwargs


@di.provide_argspec_lazy(names=['arg1'])
def omg2(arg1, default=True, nil=None, *args, **kwargs):
    print 'omg', arg1, default, nil, args, kwargs


# omg2 = di.provide_argspec_lazy(omg)
# omg3 = di.provide_argspec_lazy(['arg1'], omg)

di.register_instance('arg1', 'injected_arg1')

# omg10 = di.provide_args(['arg1'], omg)
#
# omg11 = di.provide_argspec(omg, keys=['arg1'])

print "reloaded"
