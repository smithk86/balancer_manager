#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='py_balancer_manager',
    version='3.0.0-dev',
    description="Library for programatically interacting with Apache's mod_proxy_balancer management interface",
    author='Kyle Smith',
    author_email='smithk86@gmail.com',
    url='https://github.com/smithk86/balancer_manager',
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
        'aiohttp==3.5.4',
        'beautifulsoup4==4.7.1',
        'pytz==2019.1',
        'tzlocal==1.5.1',
        'python-dateutil==2.8.0',
        'packaging==19.0'
    ],
    setup_requires=[
        'pytest-runner'
    ],
    tests_require=[
        'pytest',
        'pytest-asyncio',
        'docker'
    ]
)
