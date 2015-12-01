import six

from mainline.provider import IProvider, ScopeProvider


class CatalogMeta(type):
    def __new__(mcs, class_name, bases, attributes):
        # providers = {}
        #
        # for base in bases:
        #     if not isinstance(base, DiCatalog):
        #         continue
        #     providers.update(base.providers)
        #
        # providers.update({k: v for k, v in six.iteritems(attributes)
        #                   if isinstance(v, Provider)})

        cls = type.__new__(mcs, class_name, bases, attributes)

        providers = {k: v for k, v in six.iteritems(attributes)
                     if isinstance(v, IProvider)}
        cls._providers = providers

        return cls


@six.add_metaclass(CatalogMeta)
class Catalog(object):
    @classmethod
    def get_providers(cls):
        return cls._providers


class ScopeProviderDecorator(object):
    _provider_cls = ScopeProvider

    def __init__(self, scope):
        self.scope = scope

    def __call__(self, factory):
        provider = self._provider_cls(self.scope, factory)
        return provider
