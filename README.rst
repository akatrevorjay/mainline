mainline
========

Simple yet powerful python dependency injection.

Tested with Python 2.7, 3.4, 3.5.

|Test Status| |Coverage Status| |Documentation Status|


Installation
------------

.. code:: sh

    pip install mainline


Usage
-----

First things first, create your instance of :class:`~mainline.di.Di`:

    >>> from mainline import Di
    >>> di = Di()


Simple factory registration and resolution of an instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When registering a factory, you can specify a scope. The factory provided will be called to construct an instance once in the scope provided.
After that, the already constructed product of the factory will be injected for all calls to :func:`~mainline.di.Di.inject` with the registered key in the specified scope.

For example:

- A factory registered with a :class:`~mainline.scope.NoneScope` will construct an instance every time :func:`~mainline.di.Di.inject` is called with the registered key.
- A factory registered with a :class:`~mainline.scope.GlobalScope` will construct one instance ever.
- A factory registered with a :class:`~mainline.scope.ProcessScope` will generate an instance once per process.
- A factory registered with a :class:`~mainline.scope.ThreadScope` will generate an instance once per thread.

Scopes can be passed to :func:`~mainline.di.Di.register_factory` as scope objects (eg factory callable), or as strings (e.g. :class:`~mainline.scope.NoneScope` is aliased to `'none'`, :class:`~mainline.scope.GlobalScope` is aliased to `'global'`).

The default scope is :class:`~mainline.scope.NoneScope`, which means a new instance is created every time. The only exception to this rule is :func:`~mainline.di.Di.set_instance`, which defaults to a :class:`~mainline.scope.GlobalScope` if no provider exists under this key.

Scopes available by default for factory registration are: :class:`~mainline.scope.GlobalScope` (:class:`~mainline.scope.SingletonScope`), :class:`~mainline.scope.ThreadScope`, :class:`~mainline.scope.ProcessScope` and :class:`~mainline.scope.NoneScope`.
However, you may provide your own custom scopes as well by providing any object class/instance that supports a :class:`collections.MutableMapping` interface.

.. testsetup::
    >>> di = Di()

.. code::

    >>> @di.register_factory('apple', scope='global')
    ... def apple():
    ...    return 'apple'
    >>> di.resolve('apple') == 'apple'
    True


Simple instance registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to inject an already instantiated object, you can do so with :func:`~mainline.di.Di.set_instance`.

If a factory has not been registered under the given key, one is created using the `default_scope` argument as it's scope,
which defaults to :class:`~mainline.scope.GlobalScope` (ie singleton).

The instance is then injected into the factory as if it had been created by it.

.. testsetup::
    >>> di = Di()

.. code::

    >>> apple = object()
    >>> di.set_instance('apple', apple)
    >>> di.resolve('apple') == apple
    True

    >>> banana = object()
    >>> di.set_instance('banana', banana, default_scope='thread')
    >>> di.resolve('banana') == banana
    True


Catalogs
~~~~~~~~

The :class:`~mainline.catalog.Catalog` class provides a declarative way to group together factories.

.. testsetup::
    >>> di = Di()

.. code::

    >>> class CommonCatalog(di.Catalog):
    ...     # di.provider() is a Provider factory.
    ...     @di.provider
    ...     def apple():
    ...         return 'apple'
    ...
    ...     # You can also give it a Provider object directly,
    ...     # albeit being a bit silly.
    ...     orange = di.Provider(lambda: 'orange')

    >>> class TestingCatalog(CommonCatalog):
    ...     @di.provider(scope='thread')
    ...     def banana():
    ...         return 'banana'

    >>> di.update(TestingCatalog)

    >>> @di.inject('apple', 'banana', 'orange')
    ... def injected(apple, banana, orange):
    ...     return apple, banana, orange

    >>> injected() == ('apple', 'banana', 'orange')
    True

    >>> class ProductionCatalog(di.Catalog):
    ...     @di.provider(scope='thread')
    ...     def banana():
    ...         return 'prod_banana'

    >>> di.update(ProductionCatalog, allow_overwrite=True)

    >>> @di.inject('apple', 'banana', 'orange')
    ... def injected(apple, banana, orange):
    ...     return apple, banana, orange

    >>> injected() == ('apple', 'prod_banana', 'orange')
    True


Di as a Catalog
^^^^^^^^^^^^^^^

Di supports the ICatalog interface as well, so you can also update Di
instances from other Di instances.

.. testsetup::
    >>> di = Di()

.. code::

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> other_di = Di()

    >>> @other_di.register_factory('banana')
    ... def banana():
    ...     return 'banana'

    >>> di.update(other_di)

    >>> @di.inject('apple', 'banana')
    ... def injected(apple, banana):
    ...     return apple, banana

    >>> injected() == ('apple', 'banana')
    True


Injection of positional and keyword arguments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. testsetup::
    >>> di = Di()

.. code::

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject('apple')
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()
    True

    >>> @di.inject('apple')
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True

    >>> @di.register_factory('banana')
    ... @di.inject('apple')
    ... def banana(apple):
    ...     return 'banana', apple

    >>> @di.inject('apple', omg='banana')
    ... def injected(apple, arg1, omg=None):
    ...     return apple, arg1, omg

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True

    >>> @di.register_factory('orange')
    ... @di.inject('apple', not_an_apple='banana')
    ... def orange(apple, not_an_apple):
    ...     return 'orange', not_an_apple

    >>> @di.inject('apple', 'orange', omg='banana')
    ... def injected(apple, orange, arg1, omg=None):
    ...     return apple, orange, arg1, omg

    >>> injected('arg1') == (apple(), orange(), 'arg1', banana())
    True


Provider keys don't have to be strings

.. code::

    >>> class Test(object):
    ...     pass

    >>> # Thread scopes are stored in a thread local
    ... @di.register_factory(Test, scope='thread')
    ... def test_factory():
    ...     return Test()

    >>> @di.inject(Test)
    ... def injected(test):
    ...     return test

    >>> isinstance(injected(), Test)
    True


Injection on object init

.. code::

    >>> @di.inject('apple')
    ... class Injectee(object):
    ...     def __init__(self, apple):
    ...         self.apple = apple

    >>> Injectee().apple == apple()
    True


Injection as a classproperty
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. testsetup::
    >>> di = Di()

.. code::

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject_classproperty('apple')
    ... class Injectee(object):
    ...     pass

    >>> Injectee.apple == apple()
    True


Auto injection based on name in argspec
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Do yourself a favor and use this sparingly. The magic on this one is
real.

.. testsetup::
    >>> di = Di()

.. code::

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.auto_inject()
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()
    True

    >>> @di.auto_inject('apple')
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True

    >>> @di.register_factory('banana')
    ... @di.auto_inject()
    ... def banana(apple):
    ...     return 'banana', apple

    >>> @di.auto_inject()
    ... def injected(apple, arg1, banana=None):
    ...     return apple, arg1, banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True


Running tests
-------------

Tox is used to handle testing multiple python versions.

.. code:: sh

    tox


.. |Test Status| image:: https://circleci.com/gh/vertical-knowledge/mainline.svg?style=svg
   :target: https://circleci.com/gh/vertical-knowledge/mainline
.. |Coverage Status| image:: https://coveralls.io/repos/vertical-knowledge/mainline/badge.svg?branch=develop&service=github
   :target: https://coveralls.io/github/vertical-knowledge/mainline?branch=develop
.. |Documentation Status| image:: https://readthedocs.org/projects/mainline/badge/?version=latest
   :target: http://mainline.readthedocs.org/en/latest/?badge=latest
