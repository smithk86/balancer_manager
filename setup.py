#!/usr/bin/env python

import os.path

from setuptools import setup, find_packages


# get the version to include in setup()
dir_ = os.path.abspath(os.path.dirname(__file__))
with open(f'{dir_}/py_balancer_manager/__init__.py') as fh:
    for line in fh:
        if '__VERSION__' in line:
            exec(line)


setup(
    name='py_balancer_manager',
    version=__VERSION__,
    description="Library for programatically interacting with Apache's mod_proxy_balancer management interface",
    author='Kyle Smith',
    author_email='smithk86@gmail.com',
    url='https://github.com/smithk86/py-balancer-manager',
    entry_points={
        'console_scripts': [
            'balancer-manager-manage=py_balancer_manager.cli:manage',
            'balancer-manager-validate=py_balancer_manager.cli:validate'
        ]
    },
    packages=[
        'py_balancer_manager',
        'py_balancer_manager.cli',
    ],
    install_requires=[
        'beautifulsoup4',
        'dateparser',
        'httpx==0.18.1',
        'packaging',
        'pytz',
        'termcolor',
        'tzlocal'
    ],
    setup_requires=[
        'pytest-runner'
    ],
    tests_require=[
        'docker',
        'pytest',
        'pytest-asyncio',
        'pytest-helpers-namespace'
    ]
)
