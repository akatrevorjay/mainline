import inspect
import six
import abc

from mainline.utils import ProxyMutableMapping
from mainline.provider import IProvider

_sentinel = object()
_provider_mapping_factory = dict


class ProviderMapping(ProxyMutableMapping):
    '''
    Mixin to provide mapping interface on providers
    '''

    _mapping_factory = _provider_mapping_factory

    def __init__(self, *args, **kwargs):
        if self.__class__._providers:
            self._providers = self.__class__._providers.copy()
        else:
            self._providers = self._mapping_factory()
        super(ProviderMapping, self).__init__(self._providers)
        self.update(dict(*args, **kwargs))

    def update(self, *args, **kwargs):
        '''
        Updates our providers with either an ICatalog subclass/instance or a mapping.
        If mapping is an ICatalog, we update from it's ._providers attribute.

        :param mapping: Mapping to update from.
        :type mapping: ICatalog or Di or collections.Mapping
        '''
        # If we only have one argument
        if len(args) == 1 and not kwargs:
            # If ths one arg happens to be an ICatalog subclass
            single_arg = args[0]
            if inspect.isclass(single_arg) and issubclass(single_arg, ICatalog) or isinstance(single_arg, ICatalog):
                args = (single_arg._providers,)
        super(ProviderMapping, self).update(dict(*args, **kwargs))


class ICatalog(object):
    '''
    Inherit from this class to note that you support the ICatalog interface
    '''

    _providers = None


class CatalogMeta(abc.ABCMeta):
    '''
    Meta class used to populate providers from attributes of Catalog subclass declarations.
    '''

    _provider_mapping_factory = _provider_mapping_factory

    def __new__(mcs, class_name, bases, attributes):
        cls = super(CatalogMeta, mcs).__new__(mcs, class_name, bases, attributes)

        # We may already have providers. If so, make a copy.
        if cls._providers:
            cls._providers = cls._providers.copy()
        else:
            cls._providers = mcs._provider_mapping_factory()

        cls._providers.update(
                {k: v for k, v in six.iteritems(attributes)
                 if isinstance(v, IProvider)}
        )

        return cls


@six.add_metaclass(CatalogMeta)
class Catalog(ICatalog, ProviderMapping):
    pass
