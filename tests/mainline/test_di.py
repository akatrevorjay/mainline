"""
Note that the docs and the README double as tests themselves.
"""

import mock
import pytest
import itertools

import mainline


class TestDi(object):
    # Set of all possible scope values
    all_scopeish = set(itertools.chain(*mainline.Di.scopes.items()))

    @pytest.fixture()
    def di(self):
        di = mainline.Di()
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
        with pytest.raises(mainline.UnresolvableError):
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

        factory.reset_mock()
        # Force that we give a different object
        factory.return_value = object()
        if scope in ['none', di.scopes['none']]:
            # NoneScope always returns a new instance
            second_instance = di.resolve(key)
            factory.assert_called_once_with()
            assert id(second_instance) != id(instance)
        else:
            # Test that provider returns the same object for multiple resolutions
            second_instance = di.resolve(key)
            di.resolve()
            factory.assert_not_called()
            assert id(second_instance) == id(instance)

    @pytest.mark.parametrize('deps', [('dep0',), ('dep0', 'dep1')])
    def test_depends_on(self, di, deps):

        @di.depends_on(*deps)
        def test():
            pass

        assert di.get_deps(test) == set(deps)
