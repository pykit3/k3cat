# DO NOT EDIT!!! built with `python _building/build_setup.py`
import setuptools
setuptools.setup(
    name="k3cat",
    packages=["k3cat"],
    version="0.1.0",
    license='MIT',
    description='Just like nix command cat or tail, it continuously scan a file line by line.',
    long_description='# k3cat\n\n[![Action-CI](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml/badge.svg)](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml)\n[![Build Status](https://travis-ci.com/pykit3/k3cat.svg?branch=master)](https://travis-ci.com/pykit3/k3cat)\n[![Documentation Status](https://readthedocs.org/projects/k3cat/badge/?version=stable)](https://k3cat.readthedocs.io/en/stable/?badge=stable)\n[![Package](https://img.shields.io/pypi/pyversions/k3cat)](https://pypi.org/project/k3cat)\n\nJust like nix command cat or tail, it continuously scan a file line by line.\n\nk3cat is a component of [pykit3] project: a python3 toolkit set.\n\n\nJust like nix command cat or tail, it continuously scan a file line by line.\n\nIt provides with two way for user to handle lines: as a generator or specifying\na handler function.\n\nIt also remembers the offset of the last scanning in a file in `/tmp/`.\nIf a file does not change(inode number does not change), it scans from the last\noffset, or it scan from the first byte.\n\n\n\n\n# Install\n\n```\npip install k3cat\n```\n\n# Synopsis\n\n```python\n\nimport sys\n\nimport k3cat\n\nfn = sys.argv[1]\nfor x in k3cat.Cat(fn, strip=True).iterate(timeout=0):\n    print(x)\n\n```\n\n#   Author\n\nZhang Yanpo (张炎泼) <drdr.xp@gmail.com>\n\n#   Copyright and License\n\nThe MIT License (MIT)\n\nCopyright (c) 2015 Zhang Yanpo (张炎泼) <drdr.xp@gmail.com>\n\n\n[pykit3]: https://github.com/pykit3',
    long_description_content_type="text/markdown",
    author='Zhang Yanpo',
    author_email='drdr.xp@gmail.com',
    url='https://github.com/pykit3/k3cat',
    keywords=['python'],
    python_requires='>=3.0',

    install_requires=['k3ut<0.2,>=0.1.15', 'k3fs<=0.2.0,>=0.1.0', 'k3utfjson<0.2,>=0.1.1', 'k3thread<0.2,>=0.1.0', 'k3proc<0.3.0,>=0.2.13', 'k3confloader<0.2,>=0.1.1', 'k3portlock<0.2,>=0.1.1'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries',
    ] + ['Programming Language :: Python :: 3'],
)
