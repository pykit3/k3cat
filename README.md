# k3cat

[![Action-CI](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml/badge.svg)](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml)
[![Documentation Status](https://readthedocs.org/projects/k3cat/badge/?version=stable)](https://k3cat.readthedocs.io/en/stable/?badge=stable)
[![Package](https://img.shields.io/pypi/pyversions/k3cat)](https://pypi.org/project/k3cat)

Just like nix command cat or tail, it continuously scan a file line by line.

k3cat is a component of [pykit3] project: a python3 toolkit set.


Just like nix command cat or tail, it continuously scan a file line by line.

It provides with two way for user to handle lines: as a generator or specifying
a handler function.

It also remembers the offset of the last scanning in a file in `/tmp/`.
If a file does not change(inode number does not change), it scans from the last
offset, or it scan from the first byte.




# Install

```
pip install k3cat
```

# Synopsis

```python

import sys

import k3cat

fn = sys.argv[1]
for x in k3cat.Cat(fn, strip=True).iterate(timeout=0):
    print(x)

```

#   Author

Zhang Yanpo (张炎泼) <drdr.xp@gmail.com>

#   Copyright and License

The MIT License (MIT)

Copyright (c) 2015 Zhang Yanpo (张炎泼) <drdr.xp@gmail.com>


[pykit3]: https://github.com/pykit3