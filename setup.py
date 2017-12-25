#!/usr/bin/env python

from setuptools import setup
import sys

conf = dict(
    setup_requires=['pbr>=1.9', 'setuptools>=17.1'],
    pbr=True,
)

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
if needs_pytest:
    conf['setup_requires'].append('pytest-runner')

setup(**conf)
