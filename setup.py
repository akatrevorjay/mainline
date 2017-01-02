from setuptools import setup
import sys

__version__ = 'unknown'  # This is ovewritten by the execfile below
exec (open('mainline/_version.py').read())

def parse_requirements(filename):
    ret = [line.strip() for line in open(filename).read().splitlines()]
    ret = [x for x in ret if x and not x[0] in ['#', '-']]
    return ret

conf = dict(
    name='mainline',
    description='Simple yet powerful python dependency injection for py2/py3k',
    url='http://github.com/akatrevorjay/mainline',
    author='Trevor Joynson',
    author_email='github@skywww.net',
    license='GPL',
    keywords=['dependency', 'injection', 'ioc'],
    classifiers=[],

    version=__version__,
    packages=['mainline'],

    install_requires=parse_requirements('requirements/install.txt'),
    tests_require=parse_requirements('requirements/test.txt'),

    # This gets populated below if necessary
    setup_requires=[],
)

conf['download_url'] = '{url}/tarball/{version}'.format(**conf)

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
if needs_pytest:
    conf['setup_requires'].append('pytest-runner')

setup(**conf)
