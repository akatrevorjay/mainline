import collections
import sys

import six

IS_PYPY = '__pypy__' in sys.builtin_module_names


def _get_object_init():
    if six.PY3 or IS_PYPY:
        return six.get_unbound_function(object.__init__)


OBJECT_INIT = _get_object_init()


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


class ProxyMutableMapping(collections.MutableMapping):
    def __init__(self, mapping):
        self.__mapping = mapping

    _fancy_repr = True

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
