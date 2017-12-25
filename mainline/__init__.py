"""
mainline: simple python dependency injection.
"""
import pkg_resources
__version__ = pkg_resources.get_distribution(__name__).version

from mainline.exceptions import DiError, UnresolvableError, UnprovidableError

from mainline.di import Di
from mainline.catalog import Catalog
from mainline.provider import Provider, provider_factory
from mainline.scope import NoneScope, GlobalScope, ProcessScope, ThreadScope, \
    ProxyScope, NamespacedProxyScope
