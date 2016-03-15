#!/usr/bin/env python

from setuptools import setup

setup(
    name='py_balancer_manager',
    version='1.3.1-dev',
    description="Library for programatically interacting with Apache's mod_proxy_balancer management interface",
    author='Kyle Smith',
    author_email='smithk86@gmail.com',
    url='https://github.com/smithk86/balancer_manager',
    install_requires=[
        'requests',
        'beautifulsoup4'
    ]
)
