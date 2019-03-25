#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()


requirements = [
    'aiohttp==3.5.4',
    'aioboto3==6.2.2',
    'aioredis==1.2.0'
]

test_requirements = [
    'pytest',
    'pytest-asyncio',
    'flake8'
]

setup(
    name='aiosmpp',
    version='0.1.0',
    description="Async SMPP framework",
    long_description=readme,
    author="Terry Cain",
    author_email='terry@terrys-home.co.uk',
    url='https://github.com/terrycain/aiosmpp',
    packages=find_packages(include=['aiosmpp*']),
    include_package_data=True,
    install_requires=requirements,
    license="Apache 2",
    zip_safe=False,
    keywords='aiosmpp',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
