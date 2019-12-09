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
    """
    Proxies access to an existing dict-like object.

    >>> a = dict(whoa=True, hello=[1,2,3], why='always')
    >>> b = ProxyMutableMapping(a)

    Nice reprs:

    >>> b
    <ProxyMutableMapping {...}>

    Setting works as you'd expect:

    >>> a['nice'] = b['nice'] = False
    >>> a['whoa'] = b['whoa'] = 'yeee'

    Checking that the changes are in fact being performed on the proxied object:

    >>> b == a
    True

    """

    def __init__(self, mapping, fancy_repr=True, dictify_repr=False):
        """
        :param collections.MutableMapping mapping: Dict-like object to wrap
        :param bool fancy_repr: If True, show fancy repr, otherwise just show dict's
        :param bool dictify_repr: If True, cast mapping to a dict on repr
        """
        self.__fancy_repr = fancy_repr
        self.__dictify_repr = dictify_repr

        self._set_mapping(mapping)

    def __repr__(self):
        if not self.__fancy_repr:
            return '%s' % dict(self)

        mapping = self.__mapping
        if self.__dictify_repr:
            mapping = dict(mapping)

        return '<%s %s>' % (self.__class__.__name__, mapping)

    def _set_mapping(self, mapping):
        self.__mapping = mapping

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
