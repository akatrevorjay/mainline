import mock
import pytest
import itertools

from mainline import Di, Catalog, UnresolvableError, Provider


class TestDi(object):
    # Set of all possible scope values
    all_scopeish = set(itertools.chain(*Di.scopes.items()))

    @pytest.fixture()
    def di(self):
        di = Di()
        return di

    @pytest.fixture(params=['mock_provider0', 'mock_provider1'])
    def provider_kv(self, di, request):
        key = request.param
        provider = mock.MagicMock(return_value=object())
        di.providers[key] = provider

        def fin():
            del di.providers[key]

        request.addfinalizer(fin)
        return key, provider

    @pytest.fixture(params=dict(
            mock_deps0=set(['dep0', 'dep1', 'dep2']),
            mock_deps1=set(['dep0']),
    ).items())
    def dependency_kv(self, di, request):
        key, deps = request.param
        di.dependencies[key] = deps
        for dep in deps:
            di.providers[dep] = mock.MagicMock(return_value=object())

        def fin():
            del di.dependencies[key]
            for dep in deps:
                del di.providers[dep]

        request.addfinalizer(fin)
        return key, deps

    def test_assert_test_env(self, di):
        assert self.all_scopeish

    def test_set_instance(self, di, provider_kv):
        key, provider = provider_kv

        instance = mock.MagicMock()
        di.set_instance(key, instance)
        provider.set_instance.assert_called_once_with(instance)

    def test_get_provider(self, di, provider_kv):
        key, provider = provider_kv
        assert di.providers[key] is provider

    def test_get_provider_404(self, di):
        with pytest.raises(KeyError):
            di.providers['i_dont_exist']

    def test_get_deps(self, di, dependency_kv):
        key, deps = dependency_kv
        assert di.get_deps(key) == deps

    def test_get_missing_deps(self, di):
        key = 'mock_missing_deps'
        deps = ['missing_dep0', 'missing_dep1']
        di.dependencies[key] = set(deps)

        missing = di.get_missing_deps(key)
        assert set(missing) == set(deps)

    def test_iresolve(self, di, provider_kv):
        key, provider = provider_kv
        assert list(di.iresolve(key)) == [provider.return_value]

    def test_resolve(self, di, provider_kv):
        key, provider = provider_kv
        assert di.resolve(key) == provider.return_value
        provider.assert_called_with()

    def test_resolve_unresolvable(self, di):
        di.dependencies['missing_deps'] = set(['missing_dep0'])
        di.providers['missing_deps'] = mock.MagicMock()
        with pytest.raises(UnresolvableError):
            di.resolve('missing_deps')

    def test_resolve_many(self, di):
        providers = dict(
                mock_provider_uno=mock.MagicMock(return_value=object()),
                mock_provider_dos=mock.MagicMock(return_value=object()),
        )
        di.providers.update(providers)

        items = [(k, v.return_value) for k, v in providers.items()]
        assert di.resolve(*[x[0] for x in items]) == [x[1] for x in items]

    def test_resolve_deps(self, di, dependency_kv):
        key, deps = dependency_kv
        values = [di.resolve(dep) for dep in deps]
        assert set(di.resolve_deps(key)) == set(values)

    @pytest.mark.parametrize('scope', all_scopeish)
    def test_resolve_factory_for_each_scope(self, di, scope):
        key = 'test_factory_scope_%s' % scope
        factory = mock.MagicMock(return_value=object())
        di.register_factory(key, factory, scope=scope)

        instance = di.resolve(key)
        factory.assert_called_once_with()
        assert instance is factory.return_value

    @pytest.mark.parametrize('deps', [('dep0',), ('dep0', 'dep1')])
    def test_depends_on(self, di, deps):
        @di.depends_on(*deps)
        def test():
            pass

        assert di.get_deps(test) == set(deps)

    def test_example_resolve(self, di):
        @di.register_factory('apple')
        def apple():
            return 'apple'

        assert di.resolve('apple') == 'apple'

    def test_example_set_instance(self, di):
        apple = object()
        di.set_instance('apple', apple)
        assert di.resolve('apple') == apple

        # If no factory is registered already with this key, one is created using the optional default_scope keyword argument, which defaults to singleton.
        banana = object()
        di.set_instance('banana', banana, default_scope='singleton')
        assert di.resolve('banana') == banana

    def test_example_inject(self, di):
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

    def test_example_inject_classproperty(self, di):
        @di.register_factory('apple')
        def apple():
            return 'apple'

        @di.inject_classproperty('apple')
        class Injectee(object):
            pass

        assert Injectee.apple == apple()

    def test_example_auto_inject(self, di):
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

    def test_example_catalog(self, di):
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

    def test_example_di_as_catalog(self, di):
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
