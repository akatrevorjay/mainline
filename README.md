mainline
========

Simple yet powerful python dependency injection.

Tested with Python 2.7, 3.4, 3.5.

[![Test Status](https://circleci.com/gh/vertical-knowledge/mainline.svg?style=svg)](https://circleci.com/gh/vertical-knowledge/mainline) [![Coverage Status](https://coveralls.io/repos/vertical-knowledge/mainline/badge.svg?branch=develop&service=github)](https://coveralls.io/github/vertical-knowledge/mainline?branch=develop) [![Documentation Status](https://readthedocs.org/projects/mainline/badge/?version=latest)](http://mainline.readthedocs.org/en/latest/?badge=latest)


Installation
------------

```sh
pip install mainline
```

Examples
--------

### Simple factory registration and resolution of an instance

```py
from mainline import Di
di = Di()

# The default scope is singleton, but thread and process are also
# supported. Any MutableMapping supporting object can also be given.
@di.register_factory('apple', scope='singleton')
def apple():
    return 'apple'

assert di.resolve('apple') == 'apple'
```

### Simple instance registration

```py
from mainline import Di
di = Di()

apple = object()
di.set_instance('apple', apple)
assert di.resolve('apple') == apple

# If no factory is registered already with this key, one is created
# using the optional default_scope keyword argument, which defaults
# to singleton.
banana = object()
di.set_instance('banana', banana, default_scope='singleton')
assert di.resolve('banana') == banana
```

### Injection of positional and keyword arguments

```py
from mainline import Di
di = Di()

@di.register_factory('apple')
def apple():
    return 'apple'

@di.inject('apple')
def injected(apple):
    return apple

assert injected() == apple()

@di.inject('apple')
def injected(apple, arg1):
    return apple, arg1

assert injected('arg1') == (apple(), 'arg1')

@di.register_factory('banana')
@di.inject('apple')
def banana(apple):
    return 'banana', apple

@di.inject('apple', omg='banana')
def injected(apple, arg1, omg=None):
    return apple, arg1, omg

assert injected('arg1') == (apple(), 'arg1', banana())

@di.register_factory('orange')
@di.inject('apple', not_an_apple='banana')
def orange(apple, not_an_apple):
    return 'orange', not_an_apple

@di.inject('apple', 'orange', omg='banana')
def injected(apple, orange, arg1, omg=None):
    return apple, orange, arg1, omg

assert injected('arg1') == (apple(), orange(), 'arg1', banana())

'''
Provider keys don't have to be strings
'''

class Test(object):
    pass

# Thread scopes are stored in a thread local
@di.register_factory(Test, scope='thread')
def test_factory():
    return Test()

@di.inject(Test)
def injected(test):
    return test

assert isinstance(injected(), Test)

'''
Injection on object init
'''

@di.inject('apple')
class Injectee(object):
    def __init__(self, apple):
        self.apple = apple

assert Injectee().apple == apple()
```

### Injection as a classproperty

```py
from mainline import Di
di = Di()

@di.register_factory('apple')
def apple():
    return 'apple'

@di.inject_classproperty('apple')
class Injectee(object):
    pass

assert Injectee.apple == apple()
```

### Auto injection based on name in argspec

Do yourself a favor and use this sparingly. The magic on this one is real.

```py
from mainline import Di
di = Di()

@di.register_factory('apple')
def apple():
    return 'apple'

@di.auto_inject()
def injected(apple):
    return apple

assert injected() == apple()

@di.auto_inject('apple')
def injected(apple, arg1):
    return apple, arg1

assert injected('arg1') == (apple(), 'arg1')

@di.register_factory('banana')
@di.auto_inject()
def banana(apple):
    return 'banana', apple

@di.auto_inject()
def injected(apple, arg1, banana=None):
    return apple, arg1, banana

assert injected('arg1') == (apple(), 'arg1', banana())
```

### Catalogs

Catalogs provide a declarative way to group together factories.

```py
class CommonCatalog(Catalog):
    orange = Provider(lambda: 'orange')

    @di.provider()
    def apple():
        return 'apple'

class TestingCatalog(CommonCatalog):
    @di.provider(scope='thread')
    def banana():
        return 'banana'

di.update(TestingCatalog)

@di.inject('apple', 'banana', 'orange')
def injected(apple, banana, orange):
    return apple, banana, orange

assert injected() == ('apple', 'banana', 'orange')

class ProductionCatalog(Catalog):
    @di.provider()
    def orange():
        # Not really an orange now is it?
        return 'not_an_orange'

    @di.provider(scope='thread')
    def banana():
        return 'banana'

di.update(ProductionCatalog)

@di.inject('apple', 'banana', 'orange')
def injected(apple, banana, orange):
    return apple, banana, orange

assert injected() == ('apple', 'banana', 'not_an_orange')
```

#### Di as a Catalog

Di supports the ICatalog interface as well, so you can also update Di instances from other Di instances.

```py
from mainline import Di
di = Di()

@di.register_factory('apple')
def apple():
    return 'apple'

other_di = Di()

@other_di.register_factory('banana')
def banana():
    return 'banana'

di.update(other_di)

@di.inject('apple', 'banana')
def injected(apple, banana):
    return apple, banana

assert injected() == ('apple', 'banana')
```

Running tests
-------------

```sh
# From git checkout:
python setup.py test
```
