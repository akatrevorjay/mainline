import mock

import test_di


class TestDi(test_di.TestDi):
    def test_inject_annotations(self, di, dependency_kv):
        key, deps = dependency_kv

        providers = dict(
            mock_provider_uno=mock.MagicMock(return_value=object()), )
        di.providers.update(providers)

        funcs = []

        def _uno_func(fn):
            funcs.append(fn)
            return fn

        @_uno_func
        @di.auto_inject()
        def _ai_inject_annotation(arg1: 'mock_provider_uno'):
            return arg1

        @_uno_func
        @di.auto_inject()
        def _ai_inject_annotation_with_return(
                arg1: 'mock_provider_uno') -> object:
            return arg1

        @_uno_func
        @di.auto_inject()
        def _ai_with_annotation(mock_provider_uno: 'an_annotation'):
            return mock_provider_uno

        @_uno_func
        @di.auto_inject('mock_provider_uno')
        def _ai_arglimited_inject_annotation(arg1: 'mock_provider_uno'):
            return arg1

        @_uno_func
        @di.auto_inject(arg1='mock_provider_uno')
        def _ai_kwoverride_with_annotation(arg1: 'an_annotation'):
            return arg1

        mpu = providers['mock_provider_uno']
        for f in funcs:
            value = f()
            assert value == mpu.return_value
