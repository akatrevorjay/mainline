import functools
import inspect

import six
import wrapt

from mainline.exceptions import DiError
from mainline.utils import OBJECT_INIT, classproperty

try:
    from inspect import FullArgSpec as ArgSpec
    from inspect import getfullargspec as getargspec
except ImportError:
    from inspect import ArgSpec, getargspec


class Injector(object):
    def __init__(self, di):
        self.di = di

    def __call__(self, wrapped):
        raise NotImplementedError

    def decorate(self, wrapped):
        raise NotImplementedError


class CallableInjector(Injector):
    def __init__(self, di, *args, **kwargs):
        super(CallableInjector, self).__init__(di)
        self.args = args
        self.kwargs = kwargs

    def __call__(self, wrapped):
        if isinstance(wrapped, six.class_types):
            cls = wrapped
            try:
                cls_init = six.get_unbound_function(cls.__init__)
                assert cls_init is not OBJECT_INIT
            except (AttributeError, AssertionError):
                raise DiError('Class %s has no __init__ to inject' % cls)
            cls.__init__ = self(cls_init)
            return cls

        if not any([self.args, self.kwargs]):
            self.injectables = self.di.get_deps(wrapped)
        else:
            self.injectables = []
            if self.args:
                self.injectables.extend(self.args)
            if self.kwargs:
                self.injectables.extend(self.kwargs.values())
            self.di.depends_on(*self.injectables)(wrapped)

        return self.decorate(wrapped)


class SpecInjector(CallableInjector):
    def decorate(self, wrapped):
        # Remove the number of args from the wrapped function's argspec
        spec = getargspec(wrapped)
        new_args = spec.args[len(self.args):]

        # Update argspec
        spec = ArgSpec(new_args, *spec[1:])

        @wrapt.decorator(adapter=spec)
        def decorator(wrapped, instance, args, kwargs):
            injected_args = list(self.di.iresolve(*self.args))
            injected_kwargs = {k: self.di.resolve(v) for k, v in six.iteritems(self.kwargs)}

            if args:
                injected_args.extend(args)
            if kwargs:
                injected_kwargs.update(kwargs)

            return wrapped(*injected_args, **injected_kwargs)

        return decorator(wrapped)


class AutoSpecInjector(CallableInjector):
    def decorate(self, wrapped):
        spec = getargspec(wrapped)

        def decorator(*args, **kwargs):
            if self.injectables:
                injectables = self.injectables
            else:
                # TODO This is too much access..
                injectables = self.di.providers.keys()

            injected_args = []
            args_cur_index = 0
            for arg in spec.args:
                arg = self.kwargs.pop(arg, arg)
                if arg in injectables:
                    obj = self.di.resolve(arg)
                    injected_args.append(obj)
                else:
                    try:
                        injected_args.append(args[args_cur_index])
                    except IndexError:
                        # This means there aren't enough args given, which means this will most likely result in
                        # TypeError. Just let that happen, python is an adults only playground ;)
                        continue
                    args_cur_index += 1
            remaining_args = args[args_cur_index:]
            if remaining_args:
                injected_args.extend(remaining_args)

            injected_kwargs = {k: self.di.resolve(v) for k, v in six.iteritems(self.kwargs)}
            if kwargs:
                injected_kwargs.update(kwargs)

            return wrapped(*injected_args, **injected_kwargs)

        return decorator


class ClassPropertyInjector(Injector):
    def __init__(self, di, key, name=None, replace_on_access=False):
        super(ClassPropertyInjector, self).__init__(di)
        self.key = key
        self.name = name
        self.replace_on_access = replace_on_access

    def _wrap_classproperty(self, cls, key, name, replace_on_access, owner=None):
        # owner is set to the instance if applicable
        val = self.di.resolve(key)
        if replace_on_access:
            setattr(cls, name, val)
        return val

    def __call__(self, klass):
        name = self.name or self.key

        # Register as dependency for klass
        self.di.depends_on(self.key)(klass)

        # Add in arguments
        partial = functools.partial(self._wrap_classproperty, klass, self.key, name, self.replace_on_access)
        # Create classproperty from it
        clsprop = classproperty(partial)

        # Attach descriptor to object
        setattr(klass, name, clsprop)

        # Return class as this is a decorator
        return klass
