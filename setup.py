#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='py_balancer_manager',
    version='1.11.0',
    description="Library for programatically interacting with Apache's mod_proxy_balancer management interface",
    author='Kyle Smith',
    author_email='smithk86@gmail.com',
    url='https://github.com/smithk86/balancer_manager',
    packages=find_packages(exclude=["*.tests", "*.tests.*", "tests.*", "tests"]),
    install_requires=[
        'requests',
        'beautifulsoup4'
    ]
)
