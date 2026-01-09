#!/usr/bin/env python
# coding: utf-8


import errno
import logging
import os
import stat
import time

import __main__
from k3confloader import conf
import k3portlock
import k3utfjson
import k3fs


logger = logging.getLogger(__name__)


no_data_timeout = 3600
read_size = 1024 * 1024 * 16
file_check_time_range = (0.5, 5.0)
stat_dir = conf.cat_stat_dir or "/tmp"
# cat_stat_dir
# specifies base dir to store offset recording file.
#
# By default it is `/tmp`.
#
# ```sh
# # cat pykitconfig
# cat_stat_dir = '/'
#
# # cat usage.py
# import k3cat
# fn = '/var/log/nginx/access.log'
# for l in fsutil.Cat(fn).iterate(timeout=3600):
#   print l
SEEK_START = "start"
SEEK_END = "end"


class CatError(Exception):
    pass


class NoData(CatError):
    pass


class NoSuchFile(CatError):
    pass


class LockTimeout(CatError):
    pass


class FakeLock(object):
    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return


class Cat(object):
    def __init__(
        self, fn, handler=None, file_end_handler=None, exclusive=True, id=None, strip=False, read_chunk_size=read_size
    ):
        """

        :param fn: specifies the file to scan.
        :param handler: specifies a callable to handle each line, if `Cat()` is not used in
        generator mode.
        It can be a callable or a list of callable.
        See method `Cat.cat()`.
        :param file_end_handler: specifies a callable when file end reached.
        Every time it scans to end of file, `file_end_handler` is called, but it is still
        able to not quit and to wait for new data for a while.
        Thus `file_end_handler` will be called more than one time.
        :param exclusive:     is `True` means at the same time there can be only one same progress
        scanning a same file, which means, `Cat` with the same `id` and the same `fn`.
        Two `Cat` instances with different id are able to scan a same file at the
        same time and they record their own offset in separate file.
        By default it is `True`.
        :param id: specifies the instance id.
        `id` is used to identify a `Cat` instance and is used as part of offset
        record file(in `/tmp/`) and is used to exclude other instance.
        See `exclusive`.
        By default `id` is the file name of the currently running python script.
        Thus normally a user does not need to specify `id` explicitly.

        :param strip:     is `True` or `False` to specifies if to strip blank chars(space, tab, `\r`
        and `\n`) before returning each line.
        By default it is `False`.
        :param read_chunk_size: is the buffer size to read data once, appropriate small `read_chunk_size`
        will return stream data quickly.
        By default it is `16*1024**2`.
        """

        self.fn = fn
        self.handler = handler
        self.file_end_handler = file_end_handler
        self.exclusive = exclusive

        if id is None:
            if hasattr(__main__, "__file__"):
                id = __main__.__file__
                id = os.path.basename(id)
                if id == "<stdin>":
                    id = "__stdin__"
            else:
                id = "__instant_command__"

        self.id = id
        self.strip = strip

        read_chunk_size = int(read_chunk_size)
        if read_chunk_size <= 0:
            read_chunk_size = read_size
        self.read_chunk_size = read_chunk_size

        self.running = None
        self.bufferred = None  # (offset, content)

        if self.handler is not None and callable(self.handler):
            self.handler = [self.handler]

    def cat(self, timeout=None, default_seek=None):
        """
        Similar to `Cat.iterate` except it blocks until timeout or reaches file end and
        let `Cat.handler` to deal with each line.
        :return: Nothing.
        """
        for line in self.iterate(timeout=timeout, default_seek=default_seek):
            for h in self.handler:
                try:
                    h(line)
                except Exception as e:
                    logger.exception(repr(e) + " while handling {line}".format(line=repr(line)))

    def iterate(self, timeout=None, default_seek=None):
        """
            Make a generator to yield every line.
            :param timeout: specifies the time in second to wait for new data.
            If timeout is `0` or smaller than `0`, it means to scan a file no more than one time:
        -   If it sees any data, it returning them until it reaches file end.
        -   If there is not any data, it raises `NoData` error.

            By default it is 3600.
            :param default_seek:
            specify a default offset when the last scanned offset is not avaliable
            or not valid.

            Not avaliable mean the stat file used to store the scanning offset is
            not exist or has broken. For example, when it is the first time to
            scan a file, the stat file will not exist.

            Not valid mean the info stored in stat file is not for the file we are
            about to scan, this will happen when the same file is deleted and then
            created, the info stored in stat file is for the deleted file not for
            the created new file.

            We will also treat the last offset stored in stat file as not valid
            if it is too small than the file size when you set `default_seek`
            to a negative number. And the absolute value of `default_seek` is
            the maximum allowed difference.

            It can take following values:

            -   fsutil.SEEK_START:
                scan from the beginning of the file.

            -   fsutil.SEEK_END:
                scan from the end of the file, mean only new data will be scanned.

            -   `x`(a positive number, includes `0`).
                scan from offset `x`.

            -   `-x`(a negative number).
                it is used to specify the maximum allowed difference between last
                offset and file size. If the difference is bigger than `x`, then
                scan from `x` bytes before the end of the file, not scan from the
                last offset.
                This is usefull when you want to scan from near the end of the file.
                Use `fsutil.SEEK_END` can not solve the problem, because it only
                take effect when the last offset is not avaliable.
            By default it is `k3cat.SEEK_START`.
            :return: a generator.
        """
        self.running = True
        try:
            for x in self._iter(timeout, default_seek):
                yield x
        finally:
            self.running = False

    def _iter(self, timeout, default_seek):
        if timeout == 0:
            # timeout at once after one read, if there is no more data in file.
            # set to -1 to prevent possible slight time shift.
            timeout = -1

        if self.exclusive:
            lck = k3portlock.Portlock(self.lock_name(), timeout=0.1)
        else:
            lck = FakeLock()

        try:
            with lck:
                for x in self._nolock_iter(timeout, default_seek):
                    yield x
        except k3portlock.PortlockTimeout:
            raise LockTimeout(self.id, self.fn, "other Cat() has been holding this lock")

    def _nolock_iter(self, timeout, default_seek):
        if timeout is None:
            timeout = no_data_timeout

        expire_at = time.time() + timeout

        while True:
            # NOTE: Opening a file and waiting for new data in it does not work.
            #
            # It has to check for file overriding on fs periodically.
            # Or it may happens that it keeps waiting for new data on a deleted
            # but opened file, while new data is actually written into a new
            # file with the same path.
            #
            # Thus we check if file changed for about 5 times(by reopening it).

            read_timeout = (expire_at - time.time()) / 5.0

            if read_timeout < file_check_time_range[0]:
                read_timeout = file_check_time_range[0]

            if read_timeout > file_check_time_range[1]:
                read_timeout = file_check_time_range[1]

            f = self.wait_open_file(timeout=expire_at - time.time())

            with f:
                try:
                    for x in self.iter_to_file_end(f, read_timeout, default_seek):
                        yield x

                    # re-new expire_at if there is any data read.
                    expire_at = time.time() + timeout
                    if time.time() > expire_at:
                        # caller expect to return at once when it has read once,
                        # timeout < 0

                        # When timeout, it means no more data will be appended.
                        # Thus the bufferred must be a whole line, even there is
                        # not a trailing '\n' presents
                        if self.bufferred is not None:
                            line = self.bufferred[1]
                            self.bufferred = None
                            yield line
                        return

                except NoData as e:
                    # NoData raises only when there is no data yield.

                    logger.info(repr(e) + " while cat: {fn}".format(fn=self.fn))

                    if time.time() > expire_at:
                        # raise last NoData
                        raise

    def wait_open_file(self, timeout):
        expire_at = time.time() + timeout
        sleep_time = 0.01
        max_sleep_time = 1

        f = self._try_open_file()
        if f is not None:
            return f

        logger.info("file not found: {fn}".format(fn=self.fn))

        while time.time() < expire_at:
            f = self._try_open_file()
            if f is not None:
                return f

            sl = min([sleep_time, expire_at - time.time()])
            logger.debug("file not found: {fn}, sleep for {sl}".format(fn=self.fn, sl=sl))
            time.sleep(sl)

            sleep_time = min([sleep_time * 1.5, max_sleep_time])

        logger.warning("file not found while waiting for it to be present: {fn}".format(fn=self.fn))

        raise NoSuchFile(self.fn)

    def iter_to_file_end(self, f, read_timeout, default_seek):
        offset = self.get_last_offset(f, default_seek)
        f.seek(offset)

        logger.info("scan {fn} from offset: {offset}".format(fn=self.fn, offset=offset))

        for line in self.iter_lines(f, read_timeout):
            logger.debug("yield:" + repr(line))
            yield line

        if self.file_end_handler is not None:
            self.file_end_handler()

    def wait_for_new_data(self, f, timeout):
        # Before full_chunk_expire_at, wait for a full chunk data to be ready to
        # maximize throughput.
        # If time exceeds full_chunk_expire_at, return True if there is any data ready.

        # insufficient chunk data return before read_timeout
        full_chunk_timeout = min([timeout * 0.5, 1])

        full_chunk_expire_at = time.time() + full_chunk_timeout
        expire_at = time.time() + timeout

        while True:
            if f.tell() + self.read_chunk_size < _file_size(f):
                return

            if f.tell() < _file_size(f) and time.time() > full_chunk_expire_at:
                return

            if time.time() >= expire_at:
                raise NoData()

            time.sleep(0.05)

    def stat_path(self):
        """
        Returns the full path of the file to store scanning offset.
        :return: string
        """
        return os.path.join(stat_dir, self.lock_name())

    def lock_name(self):
        name = os.path.realpath(self.fn)
        name = "fsutil_cat_lock_!" + self.id + "!".join(name.split("/"))
        return name

    def read_last_stat(self):
        cont = k3fs.fread(self.stat_path())
        if cont.startswith("{"):
            return k3utfjson.load(cont)

        # old format: TODO remove it

        last = cont.strip().split(" ")
        if len(last) != 3:
            raise IOError("InvalidRecordFormat", last)

        (lastino, lastsize, lastoff) = last

        lastino = int(lastino)
        lastoff = int(lastoff)

        return {
            "inode": lastino,
            "offset": lastoff,
        }

    def write_last_stat(self, f, offset):
        st = os.fstat(f.fileno())

        ino = st[stat.ST_INO]

        last = {
            "inode": ino,
            "offset": offset,
        }

        k3fs.fwrite(self.stat_path(), k3utfjson.dump(last), fsync=False)

        logger.info("position written fn=%s inode=%d offset=%d" % (self.fn, ino, offset))

    def get_last_offset(self, f, default_seek):
        st = os.fstat(f.fileno())
        ino = st[stat.ST_INO]
        size = st[stat.ST_SIZE]

        max_residual = None

        if default_seek is None or default_seek == SEEK_START:
            default_offset = 0

        elif default_seek == SEEK_END:
            default_offset = size

        elif default_seek < 0:
            max_residual = 0 - default_seek
            default_offset = max(size - max_residual, 0)

        else:
            default_offset = default_seek

        stat_file = self.stat_path()

        if not os.path.isfile(stat_file):
            return default_offset

        try:
            last = self.read_last_stat()
        except (IOError, ValueError):
            # damaged stat file
            return default_offset

        if max_residual is not None:
            if size - last["offset"] > max_residual:
                last["offset"] = size - max_residual

        if last["inode"] != ino or last["offset"] > size:
            return default_offset

        return last["offset"]

    def iter_lines(self, f, read_timeout):
        # raise NoData for the first time
        self.wait_for_new_data(f, read_timeout)

        while True:
            offset = f.tell()
            fsize = _file_size(f)
            if offset >= fsize:
                break

            try:
                while True:
                    # On Mac 17.5.0, x86_64, python 2.7.15/2.7.16:
                    # The second time calling f.readlines() returns empty list,
                    # even when in another thread something is appended.
                    # Thus we have to use f.readline(), manually deal with every
                    # line.
                    _line = f.readline(self.read_chunk_size)
                    if _line == "":
                        break

                    if self.bufferred is not None:
                        offset = self.bufferred[0]
                        _line = self.bufferred[1] + _line
                        self.bufferred = None

                    if not _line.endswith(("\r", "\n")):
                        self.bufferred = (offset, _line)
                        offset += len(_line)
                        continue

                    line = _line
                    if self.strip:
                        line = line.strip("\r\n")
                    offset += len(_line)
                    yield line

                try:
                    # try to read a full chunk
                    self.wait_for_new_data(f, read_timeout)
                except NoData:
                    pass

            finally:
                # `yield` might be interrupted by its caller. But we still need
                # to record how much data has been returned to upper level.
                self.write_last_stat(f, offset)

    def _try_open_file(self):
        try:
            f = open(self.fn)
            logger.info("file found and opened {fn}".format(fn=self.fn))
            return f
        except IOError as e:
            if e.errno == errno.ENOENT:
                pass

        return None

    def reset_stat(self):
        """
        Remove the file used to store scanning offset.
        :return: Nothing
        """
        stat_path = self.stat_path()
        if not os.path.isfile(stat_path):
            return

        os.remove(stat_path)


def _file_size(f):
    st = os.fstat(f.fileno())
    return st[stat.ST_SIZE]
