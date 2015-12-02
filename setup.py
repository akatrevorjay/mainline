from setuptools import setup
import sys

__version__ = 'unknown'  # This is ovewritten by the execfile below
exec (open('mainline/_version.py').read())

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner'] if needs_pytest else []

conf = dict(
    name='mainline',
    description='Simple yet powerful python dependency injection for py2/py3k',
    url='http://github.com/vertical-knowledge/mainline',
    author='Trevor Joynson',
    author_email='github@skywww.net',
    license='GPL',
    # keywords=[],
    # classifiers=[],

    version=__version__,
    packages=['mainline'],

    install_requires=[
        'wrapt',
    ],

    setup_requires=pytest_runner,
    tests_require=['pytest', 'mock'],
)

conf['download_url'] = '{url}/tarball/{version}'.format(**conf)

setup(**conf)
