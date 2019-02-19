#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='py_balancer_manager',
    version='2.7.1',
    description="Library for programatically interacting with Apache's mod_proxy_balancer management interface",
    author='Kyle Smith',
    author_email='smithk86@gmail.com',
    url='https://github.com/smithk86/balancer_manager',
    entry_points = {
        'console_scripts': [
            'balancer-manager-manage=py_balancer_manager.command_line:manage',
            'balancer-manager-validate=py_balancer_manager.command_line:validate',
            'balancer-manager-workflow=py_balancer_manager.command_line:workflow'
        ]
    },
    packages=[
        'py_balancer_manager'
    ],
    install_requires=[
        'requests==2.21.0',
        'beautifulsoup4==4.6.3',
        'pytz==2018.7',
        'tzlocal==1.5.1',
        'python-dateutil==2.7.5'
    ],
    setup_requires=[
        'pytest-runner'
    ],
    tests_require=[
        'pytest',
        'docker',
        'requests_mock'
    ]
)
