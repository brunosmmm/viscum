"""Setup."""

from setuptools import setup, find_packages

setup(
    name="viscum",
    version="0.1",
    packages=find_packages(),
    package_dir={'': '.'},

    install_requires=['astor'],

    author="Bruno Morais",
    author_email="brunosmmm@gmail.com",
    description="Viscum Plugin Manager",
    scripts=[],
    )
