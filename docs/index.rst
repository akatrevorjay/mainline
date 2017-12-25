.. mainline documentation master file, created by
   sphinx-quickstart on Wed Dec  2 11:41:27 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

mainline
========

.. image:: https://raw.githubusercontent.com/akatrevorjay/mainline/develop/media/logo.png
    :alt: mainline logo
    :align: center

Simple yet powerful python dependency injection.

|ci-badge| |coverage-badge| |docs-badge|

- Docs: http://mainline.readthedocs.org/en/latest
- API Docs: http://mainline.readthedocs.org/en/latest/mainline.html
- PyPi: https://pypi.python.org/pypi/mainline

.. toctree::
    :maxdepth: 3
    :hidden:

    API <mainline.rst>


Why
---

- Pure Python, so it basically works everywhere.
  Tested against cPython `3.5`, `3.6`, `3.7` in addition to `2.7`.
  PyPy/PyPy3 are also fully supported.

- Supports using function annotations in Python `3.x`.
  This is in addition to a standard syntax that works with both `3.x` and `2.7`.

- Your method signature is fully preserved, maintaining introspection ability.
  (Minus any injected arguments of course.)

- Scope is fully configurable (per injectable), giving you tight control over where an object should be shared and where it should not.

- Supports auto injection", where your argument names are used to determine what gets injected.
  It's also fully optional, as it's slightly less performant do to it's dynamic nature.

- Provider keys tend to be strings, but really any hashable object is supported, so if you prefer to use classes, go for it.

  Just keep in mind that you can't use a class as an argument name (rightfully so) in python.
  This means you can't auto inject it, for instance.
  You can simply make an alias to get both worlds, however. The world is your oyster.


Installation
------------

.. code:: sh

    pip install mainline


Usage
-----

First things first, create your instance of :class:`~mainline.di.Di`:

.. code:: python

    >>> from mainline import Di
    >>> di = Di()


Factory registration and resolution of an instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. code:: python

    >>> @di.register_factory('apple', scope='global')
    ... def apple():
    ...    return 'apple'

    >>> di.resolve('apple') == 'apple'
    True


Injection
~~~~~~~~~

Great care has been taken to maintain introspection on injection.

Using :func:`~mainline.di.Di.inject` preserves your method signature minus any injected arguments.
It also has a shortened alias for those like me who don't much love typing all of that via :func:`~mainline.di.Di.i`.


Positional arguments are injected in the order given:

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject('apple')
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()
    True


Injecting keyword arguments is straight forward, you simply hand them as keyword arguments:

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.register_factory('banana')
    ... @di.inject('apple')
    ... def banana(apple):
    ...     return 'banana', apple

    >>> @di.inject('apple', a_banana='banana')
    ... def injected(apple, arg1, a_banana=None):
    ...     return apple, arg1, a_banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True


You can inject a class-level property using :func:`~mainline.di.Di.inject_classproperty`:

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject_classproperty('apple')
    ... class Injectee(object):
    ...     pass

    >>> Injectee.apple == apple()
    True


Arguments that are not injected work as expected:

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject('apple')
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True


Injection on a class injects upon it's `__init__` method:

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.inject('apple')
    ... class Injectee(object):
    ...     def __init__(self, apple):
    ...         self.apple = apple

    >>> Injectee().apple == apple()
    True


Auto injection based on name in argspec
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Injecting providers based upon the argpsec can be done with :func:`~mainline.di.Di.auto_inject`, or it's shortened
alias :func:`~mainline.di.Di.ai`.

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> @di.register_factory('apple')
    ... def apple():
    ...     return 'apple'

    >>> @di.auto_inject()
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()
    True

    >>> @di.ai('apple')                         # alias for :func:`~mainline.di.Di.auto_inject`
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True

    >>> @di.f('banana')                         # alias for :func:`~mainline.di.Di.register_factory`
    ... @di.auto_inject()
    ... def banana(apple):
    ...     return 'banana', apple

    >>> @di.ai()                                # alias for :func:`~mainline.di.Di.auto_inject`
    ... def injected(apple, arg1, banana=None):
    ...     return apple, arg1, banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True

    >>> @di.auto_inject(renamed_banana='banana')
    ... def injected(apple, arg1, renamed_banana):
    ...     return apple, arg1, renamed_banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True



Instance registration
~~~~~~~~~~~~~~~~~~~~~

If you want to inject an already instantiated object, you can do so with :func:`~mainline.di.Di.set_instance`.

If a factory has not been registered under the given key, one is created using the `default_scope` argument as it's scope,
which defaults to :class:`~mainline.scope.GlobalScope` (ie singleton).

The instance is then injected into the factory as if it had been created by it.

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> apple = object()
    >>> di.set_instance('apple', apple)
    >>> di.resolve('apple') == apple
    True

    >>> banana = object()
    >>> di.set_instance('banana', banana, default_scope='thread')
    >>> di.resolve('banana') == banana
    True


Provider keys
-------------

Provider keys don't have to be strings.
It's just a mapping internally, so they can be any hashable object.

.. testsetup::
    >>> di = Di()

.. code:: python

    >>> class Test(object):
    ...     pass

    >>> # Thread scopes are stored in a thread local
    ... @di.register_factory(Test, scope='thread')
    ... def test_factory():
    ...     return Test()

    >>> @di.inject(test=Test)
    ... def injected(test):
    ...     return test

    >>> isinstance(injected(), Test)
    True


Catalogs
~~~~~~~~

The :class:`~mainline.catalog.Catalog` class provides a declarative way to group together factories.

.. testsetup::
    >>> di = Di()

.. code:: python

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


You can update a Di instance from another as well:

.. testsetup::
    >>> di = Di()

.. code:: python

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



Running tests
-------------

Tox is used to handle testing multiple python versions.

.. code:: sh

    tox


.. |ci-badge| image:: https://circleci.com/gh/akatrevorjay/mainline.svg?style=svg
   :target: https://circleci.com/gh/akatrevorjay/mainline  # Ignore InvalidLinkBear
.. |coverage-badge| image:: https://coveralls.io/repos/akatrevorjay/mainline/badge.svg?branch=develop&service=github
   :target: https://coveralls.io/github/akatrevorjay/mainline?branch=develop
.. |docs-badge| image:: https://readthedocs.org/projects/mainline/badge/?version=latest
   :target: http://mainline.readthedocs.org/en/latest/?badge=latest

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

