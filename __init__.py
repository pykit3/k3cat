"""
Just like nix command cat or tail, it continuously scan a file line by line.

It provides with two way for user to handle lines: as a generator or specifying
a handler function.

It also remembers the offset of the last scanning in a file in `/tmp/`.
If a file does not change(inode number does not change), it scans from the last
offset, or it scan from the first byte.

"""

# from .proc import CalledProcessError
# from .proc import ProcError

__version__ = "0.1.0"
__name__ = "k3cat"

from .cat import (
    SEEK_END,
    SEEK_START,

    CatError,
    LockTimeout,
    NoData,
    NoSuchFile,
    Cat
)
__all__ = [

    "SEEK_END",
    "SEEK_START",

    "CatError",
    "LockTimeout",
    "NoData",
    "NoSuchFile",
    "Cat",

]
