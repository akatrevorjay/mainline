import functools
import inspect
import six

from mainline.provider import IProvider, Provider

_sentinel = object()


class ProviderMapping:
    '''
    Mixin to provide mapping interface on providers
    '''

    def __contains__(self, item):
        return item in self.providers

    def __len__(self):
        return len(self.providers)

    def __iter__(self):
        return iter(self.providers)

    def __getitem__(self, item):
        return self.providers[item]

    def __setitem__(self, key, value):
        self.providers[key] = value

    def __delitem__(self, key):
        del self.providers[key]

    def keys(self):
        '''
        Returns provider keys.

        Primarily here so you can cast to dict, eg dict(di).
        '''
        return self.providers.keys()

    def update(self, mapping):
        '''
        Updates our providers with either an ICatalog subclass/instance or a mapping.
        If mapping is an ICatalog subclass, it is instantiated to provide it's mapping interface to update from.

        :param mapping: Mapping to update from.
        :type mapping: ICatalog or Di or collections.Mapping
        '''
        # If we have an ICatalog subclass, instantiate it to provide a mapping interface.
        if inspect.isclass(mapping) and issubclass(mapping, ICatalog):
            mapping = mapping()
        self.providers.update(mapping)

    @classmethod
    def provider(cls, factory=_sentinel, scope='singleton'):
        '''
        Decorator to create a provider using the given factory, and scope.
        Can also be used in a non-decorator manner.

        :param scope: Scope key, factory, or instance
        :type scope: object or callable
        :return: decorator
        :rtype: decorator
        '''
        if factory is _sentinel:
            return functools.partial(cls.provider, scope=scope)
        provider = Provider(factory, scope)
        return provider


class ICatalog(ProviderMapping, object):
    pass


class CatalogMeta(type):
    '''
    Meta class used to populate providers from attributes of Catalog subclass declarations.
    '''

    def __new__(mcs, class_name, bases, attributes):
        cls = type.__new__(mcs, class_name, bases, attributes)

        # We may already have providers. If so, make a copy.
        if hasattr(cls, 'providers'):
            cls.providers = cls.providers.copy()
        else:
            cls.providers = {}

        cls.providers.update(
                {k: v for k, v in six.iteritems(attributes)
                 if isinstance(v, IProvider)}
        )

        return cls


@six.add_metaclass(CatalogMeta)
class Catalog(ICatalog):
    pass
