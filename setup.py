from setuptools import setup
import sys

__version__ = 'unknown'  # This is ovewritten by the execfile below
exec (open('mainline/_version.py').read())

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner'] if needs_pytest else []

conf = dict(
    name='mainline',
    description='Depdendency injection for all, not just humans.',
    url='http://github.com/vkgit/mainline',
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
