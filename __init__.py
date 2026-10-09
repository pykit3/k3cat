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

from .cat import SEEK_END, SEEK_START, Cat, CatError, LockTimeout, NoData, NoSuchFile

__all__ = [
    "SEEK_END",
    "SEEK_START",
    "Cat",
    "CatError",
    "LockTimeout",
    "NoData",
    "NoSuchFile",
]


def __getattr__(name: str) -> str:
    # importlib.metadata takes about 20 ms to import, so it is loaded only
    # when __version__ is read
    if name != "__version__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib.metadata import version

    return version("k3cat")
