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


Why
---

- Pure Python, so it basically works everywhere.
  Tested against cPython `3.5`, `3.6`, `3.7` in addition to `2.7`.
  PyPy/PyPy3 are also fully supported.

- Only external dependencies are `six` and `wrapt`, both of which you're likely to already have.

- Supports using function annotations in Python `3.x`.
  This is in addition to a standard syntax that works with both `3.x` and `2.7`.

- Your method signature is fully preserved, maintaining introspection ability.
  (Minus any injected arguments of course.)

- Scope is fully configurable (per injectable), giving you tight control over where an object should be shared and where it should not.

- Supports auto injection", where your argument names are used to determine what gets injected.
  It's also fully optional, as it's slightly less performant due to it's dynamic nature.

- Provider keys tend to be strings, but really any hashable object is supported, so if you prefer to use classes, go for it.

  Just keep in mind that you can't use a class as an argument name (rightfully so) in python.
  This means you can't auto inject it, for instance.
  You can simply make an alias to get both worlds, however. The world is your oyster.

- Check out that sweet syringe.


Installation
------------

.. code:: sh

    pip install mainline


Quickstart
----------

Make sure to check the docs for more use cases!

.. code:: python

    """
    Initialize your Di instance.
    """

    >>> from mainline import Di
    >>> di = Di()

    """
    Feed it your delicious factories, optionally scoped.
    """

    >>> @di.register_factory('apple')
    ... def apple():
    ...    return 'apple'

    """
    Factories can of course be injected themselves.
    """

    >>> @di.f('banana', scope='global')     # f is syntactic sugar for register_factory
    ... def banana():
    ...    return 'banana'

    """
    Let's verify that our factories above do what they're supposed to.
    """

    >>> di.resolve('apple') == 'apple' and di.resolve('banana') == 'banana'
    True

    """
    Positional arguments are injected in the order given:
    """

    >>> @di.inject('apple')
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()   # verify
    True

    """
    Injecting keyword arguments is straight forward, you simply hand them as keyword arguments:
    """

    >>> @di.f('orange')     # alias for register_factory
    ... @di.i('apple')      # alias for inject
    ... def orange(apple):
    ...     return 'banana', apple

    >>> @di.i('apple', an_orange='orange')
    ... def injected(apple, arg1, an_orange=None):
    ...     return apple, arg1, an_orange

    >>> injected('arg1') == (apple(), 'arg1', orange())  # verify
    True

    """
    Arguments that are not injected work as expected:
    """

    >>> @di.inject('apple')
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True

    """
    Injection on a class injects upon it's `__init__` method:
    """

    >>> @di.inject('apple')
    ... class Injectee(object):
    ...     def __init__(self, apple):
    ...         self.apple = apple

    >>> Injectee().apple == apple()
    True

    """
    You can inject class-level properties using `di.inject_classproperty()`:
    """

    >>> @di.inject_classproperty('apple')
    ... class Injectee(object):
    ...     pass

    >>> Injectee.apple == apple()
    True

    """
    Injecting providers based upon the argpsec can be done with `di.auto_inject`, or it's shortened alias `di.ai()`:
    """

    >>> @di.auto_inject()
    ... def injected(apple):
    ...     return apple

    >>> injected() == apple()
    True

    >>> @di.ai('apple')             # alias for auto_inject
    ... def injected(apple, arg1):
    ...     return apple, arg1

    >>> injected('arg1') == (apple(), 'arg1')
    True

    >>> @di.auto_inject()
    ... def injected(apple, arg1, banana=None):
    ...     return apple, arg1, banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True

    >>> @di.auto_inject(renamed_banana='banana')
    ... def injected(apple, arg1, renamed_banana):
    ...     return apple, arg1, renamed_banana

    >>> injected('arg1') == (apple(), 'arg1', banana())
    True



Running tests
-------------

Tox is used to handle testing multiple python versions.

.. code:: sh

    tox


.. |ci-badge| image:: https://circleci.com/gh/akatrevorjay/mainline.svg?style=svg
   :target: https://circleci.com/gh/akatrevorjay/mainline
.. |coverage-badge| image:: https://coveralls.io/repos/akatrevorjay/mainline/badge.svg?branch=develop&service=github
   :target: https://coveralls.io/github/akatrevorjay/mainline?branch=develop
.. |docs-badge| image:: https://readthedocs.org/projects/mainline/badge/?version=latest
   :target: http://mainline.readthedocs.org/en/latest/?badge=latest

