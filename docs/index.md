# k3cat

[![Action-CI](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml/badge.svg)](https://github.com/pykit3/k3cat/actions/workflows/python-package.yml)
[![Documentation Status](https://readthedocs.org/projects/k3cat/badge/?version=stable)](https://k3cat.readthedocs.io/en/stable/?badge=stable)
[![Package](https://img.shields.io/pypi/pyversions/k3cat)](https://pypi.org/project/k3cat)

Like nix command cat or tail, continuously scan a file line by line.

k3cat is a component of [pykit3](https://github.com/pykit3) project: a python3 toolkit set.

## Installation

```bash
pip install k3cat
```

## Quick Start

```python
import k3cat

# Iterate over lines in a file
for line in k3cat.Cat('/path/to/file', strip=True).iterate(timeout=0):
    print(line)
```

## API Reference

::: k3cat

## License

The MIT License (MIT) - Copyright (c) 2015 Zhang Yanpo (张炎泼)
