from setuptools import setup, find_packages

setup(
    name="adarelib",
    version="0.1.0",
    description="Shared utilities for ADARE framework",
    author="miqsoft",
    author_email="mksaxhandball@gmail.com",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "cattrs>=23.2.3",
        "pyyaml>=6.0.1",
        "python-ulid>=2.7.0",
    ],
)
