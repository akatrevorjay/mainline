import collections
import sys

import six


def _get_object_init():
    IS_PYPY = '__pypy__' in sys.builtin_module_names
    if IS_PYPY or six.PY3:
        OBJECT_INIT = six.get_unbound_function(object.__init__)
    else:
        OBJECT_INIT = None
    return OBJECT_INIT


OBJECT_INIT = _get_object_init()


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


class ProxyMutableMapping(collections.MutableMapping):
    def __init__(self, mapping):
        self.__mapping = mapping

    _fancy_repr = False

    def __repr__(self):
        if self._fancy_repr:
            return '<%s %s>' % (self.__class__.__name__, self.__mapping)
        else:
            return '%s' % dict(self)

    def __contains__(self, item):
        return item in self.__mapping

    def __getitem__(self, item):
        return self.__mapping[item]

    def __setitem__(self, key, value):
        self.__mapping[key] = value

    def __delitem__(self, key):
        del self.__mapping[key]

    def __iter__(self):
        return iter(self.__mapping)

    def __len__(self):
        return len(self.__mapping)
