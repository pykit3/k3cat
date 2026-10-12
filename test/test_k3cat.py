import itertools
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import k3fs
import k3proc
import k3thread
import k3ut

import k3cat

dd = k3ut.dd

# xx/pykit/fsutil/test/
this_base = os.path.dirname(__file__)

pyt = sys.executable


class TestCat(unittest.TestCase):
    fn = "/tmp/pykit-cat-test-content"

    def setUp(self):
        force_remove(self.fn)
        # Each test records offsets in a new directory, so an offset left by another run cannot change its result.
        stat_dir = tempfile.TemporaryDirectory()
        self.addCleanup(stat_dir.cleanup)
        patcher = mock.patch.object(k3cat.cat, "stat_dir", stat_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        force_remove(self.fn)

    def test_entire_file(self):
        expected = [
            "a",
            "bcd",
        ]

        append_lines(self.fn, expected)

        cat = k3cat.Cat(self.fn, strip=True)
        rst = list(cat.iterate(timeout=0))

        self.assertEqual(expected, rst)

    def test_entire_large_file(self):
        expected = [
            "a" * 1024 * 32,
            "b" * 1024 * 32,
        ] * 1024

        append_lines(self.fn, expected)

        dd(os.system("ls -l /tmp/pykit*"))

        cat = k3cat.Cat(self.fn, strip=True)
        rst = list(cat.iterate(timeout=0))

        self.assertEqual(expected, rst)

    def test_half_line(self):
        n = 128

        def _append():
            for _ in range(n):
                time.sleep(0.001)
                append_bytes(self.fn, "a" * 2048)
                time.sleep(0.001)
                append_bytes(self.fn, "b" * 2048 + "\n")

        th = k3thread.daemon(_append)

        i = 0

        try:
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1):
                self.assertEqual("b", line[-1])
                i += 1
        except k3cat.NoData:
            pass

        th.join()
        self.assertEqual(n, i)

    def test_offset_record_when_destory(self):
        expected = [x * 32 for x in "qwertyuiop"]

        append_lines(self.fn, expected)
        cat_handle = k3cat.Cat(self.fn, strip=True)

        rst = list(cat_handle.iterate(timeout=0))
        self.assertEqual(expected, rst)

        # stat file was removed
        k3fs.remove(cat_handle.stat_path())
        rst.extend(cat_handle.iterate(timeout=0))
        self.assertEqual(expected * 2, rst)

        # stat file was damaged
        k3fs.fwrite(cat_handle.stat_path(), "{]")
        rst.extend(cat_handle.iterate(timeout=0))
        self.assertEqual(expected * 3, rst)

    def test_offset_record_kept_when_write_fails(self):
        # A write that fails after it starts, as on a full disk, must keep the last record. An emptied record
        # counts as damaged, so the next Cat would read the file from the start again.
        append_lines(self.fn, ["a"])
        first = list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        append_lines(self.fn, ["b"])
        # The record file is opened before f.write() refuses the bytes.
        with mock.patch.object(k3cat.cat.k3utfjson, "dump", return_value=b"{}"), self.assertRaises(TypeError):
            list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        rest = list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        self.assertEqual(["a"], first)
        self.assertEqual(["b"], rest)

    def test_data_chucked(self):
        expected = ["a" * 32]
        new_data = ["b" * 32]
        chucked = ["c" * 31]

        cat_handle = k3cat.Cat(self.fn, strip=True)
        rst = []

        append_lines(self.fn, expected)
        rst.extend(cat_handle.iterate(timeout=0))
        self.assertEqual(expected, rst)

        # file was refreshed
        os.rename(self.fn, self.fn + "_old")
        append_lines(self.fn, new_data)
        k3fs.remove(self.fn + "_old")
        rst.extend(cat_handle.iterate(timeout=0))
        self.assertEqual(expected + new_data, rst)

        # file was chucked
        k3fs.fwrite(self.fn, chucked[0])
        rst.extend(cat_handle.iterate(timeout=0))
        dd(rst)
        self.assertEqual(expected + new_data + chucked, rst)

    def test_continue_read(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        rst = []

        for i in range(1, 11):
            append_lines(self.fn, expected)

            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0))

            self.assertEqual(expected * i, rst)

    def test_continue_read_multibyte(self):
        # The recorded offset must count bytes, or the second scan starts in
        # the middle of "中".
        cat = k3cat.Cat(self.fn, strip=True)

        append_lines(self.fn, ["中"])
        first = list(cat.iterate(timeout=0))

        append_lines(self.fn, ["后"])
        second = list(cat.iterate(timeout=0))

        self.assertEqual(["中"], first)
        self.assertEqual(["后"], second)

    def test_continue_read_incomplete_line(self):
        # The recorded offset must stay at the start of a line that has no "\n" yet, or the next Cat starts
        # in the middle of "中". A line returned at the timeout is recorded, so it is not returned again.
        zhong = "中".encode()
        with open(self.fn, "wb") as f:
            f.write(b"a\n" + zhong[:2])

        first = []
        with self.assertRaises(k3cat.NoData):
            first.extend(k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1))

        with open(self.fn, "ab") as f:
            f.write(zhong[2:] + b"\nb")

        second = list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        with self.assertRaises(k3cat.NoData):
            list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        self.assertEqual(["a"], first)
        self.assertEqual(["中", "b"], second)

    def test_continue_read_after_consumer_stops(self):
        # A line is recorded as read once it is returned, even if the consumer then stops the iteration.
        append_lines(self.fn, ["a", "b", "c"])

        it = k3cat.Cat(self.fn, strip=True).iterate(timeout=0)
        first = next(it)
        it.close()

        rest = list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

        self.assertEqual("a", first)
        self.assertEqual(["b", "c"], rest)

    def test_truncate_below_multibyte_offset(self):
        # The offset after "中中中\n" is 10 bytes but 4 characters. The new
        # content is 9 bytes, so only a byte offset sees that the file shrank.
        cat = k3cat.Cat(self.fn, strip=True)

        append_lines(self.fn, ["中中中"])
        first = list(cat.iterate(timeout=0))

        k3fs.fwrite(self.fn, "abcdefgh\n")
        second = list(cat.iterate(timeout=0))

        self.assertEqual(["中中中"], first)
        self.assertEqual(["abcdefgh"], second)

    def test_truncate_while_reading(self):
        # Truncating keeps the inode, so only the size, now below the read
        # offset, makes the running scan start again from the first byte.
        append_lines(self.fn, ["a" * 32, "b" * 32])

        it = k3cat.Cat(self.fn, strip=True).iterate(timeout=1)
        rst = []
        rst.append(next(it))
        rst.append(next(it))

        k3fs.fwrite(self.fn, "c" * 8 + "\n")
        rst.append(next(it))
        it.close()

        self.assertEqual(["a" * 32, "b" * 32, "c" * 8], rst)

    def test_file_change_after_incomplete_line(self):
        # The same Cat keeps the incomplete line "ab" after a scan. It belongs to the replaced file, so it must
        # not be joined to the new file's first line.
        k3fs.fwrite(self.fn, "x\nab")
        cat = k3cat.Cat(self.fn, strip=True)

        first = []
        with self.assertRaises(k3cat.NoData):
            first.extend(cat.iterate(timeout=0.1))
        self.assertEqual(["x"], first)

        # An atomic write renames a new file over the old one, so the new file has another inode.
        k3fs.fwrite(self.fn, "cd\n", atomic=True)
        second = list(cat.iterate(timeout=0))
        self.assertEqual(["cd"], second)

        # The recorded offset is the end of the new file, so "cd" is not read again.
        with self.assertRaises(k3cat.NoData):
            list(cat.iterate(timeout=0))

    def test_truncate_after_incomplete_line(self):
        # The same Cat keeps the incomplete line "ab" at offset 2. After a truncation the scan restarts at offset
        # 0, so "ab" must not be joined to the first line read there.
        k3fs.fwrite(self.fn, "x\nab")
        cat = k3cat.Cat(self.fn, strip=True)

        first = []
        with self.assertRaises(k3cat.NoData):
            first.extend(cat.iterate(timeout=0.1))
        self.assertEqual(["x"], first)

        # Writing in place keeps the inode.
        k3fs.fwrite(self.fn, "c")
        second = list(cat.iterate(timeout=0))
        self.assertEqual(["c"], second)

        with self.assertRaises(k3cat.NoData):
            list(cat.iterate(timeout=0))

    def test_reset_stat_after_incomplete_line(self):
        # The same Cat keeps the incomplete line "ab" at offset 2. After reset_stat() the scan restarts at offset
        # 0, so "ab" must not be joined to the first line read there.
        k3fs.fwrite(self.fn, "x\nab")
        cat = k3cat.Cat(self.fn, strip=True)

        first = []
        with self.assertRaises(k3cat.NoData):
            first.extend(cat.iterate(timeout=0.1))
        self.assertEqual(["x"], first)

        cat.reset_stat()
        append_lines(self.fn, ["c"])
        second = list(cat.iterate(timeout=0))
        self.assertEqual(["x", "abc"], second)

    def test_file_change(self):
        expected = [
            "a" * 32,
            "b" * 32,
            "c" * 32,
            "d" * 32,
        ]
        rst = []
        line_read = threading.Event()

        def _override():
            for item in expected:
                line_read.clear()
                force_remove(self.fn)
                append_lines(self.fn, [item])
                dd("overrided: ", item)
                # Replace the file only after Cat read this version: a fixed
                # sleep loses a version when the reader is slow.
                line_read.wait(timeout=10)

        th = k3thread.daemon(_override)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            for line in cat.iterate(timeout=2):
                rst.append(line)
                line_read.set()
        except k3cat.NoData:
            pass

        th.join()

        self.assertEqual(expected, rst)

    def test_file_change_lost_if_too_frequently(self):
        # The minimal reopen interval to detect file change
        # is 0.5 sec, defined in fsutil/cat.py: file_check_time_range.
        # Thus the sleep must be `>=` 0.5 or there might be chance a
        # file change gets lost.
        #
        # Thus we need a case to expose this issue.
        # 2020 Jan 05 by xp

        expected = [
            "a" * 32,
            "b" * 32,
            "c" * 32,
            "d" * 32,
        ]
        rst = []

        def _override():
            for item in expected:
                force_remove(self.fn)
                append_lines(self.fn, [item])
                dd("overrided: ", item)
                time.sleep(0.3)

        th = k3thread.daemon(_override)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=2))
        except k3cat.NoData:
            pass

        th.join()

        self.assertNotEqual(expected, rst)

    def test_wait_for_file(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        rst = []

        def _append():
            time.sleep(0.1)
            append_lines(self.fn, expected)
            dd("appended")

        th = k3thread.daemon(_append)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0.4))
        except k3cat.NoData:
            pass

        th.join()

        self.assertEqual(expected, rst)

    def test_wait_for_file_timeout(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        rst = []

        def _append():
            time.sleep(0.3)
            append_lines(self.fn, expected)
            dd("appended")

        th = k3thread.daemon(_append)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0.1))

            self.fail("expect NoSuchFile to raise")
        except k3cat.NoSuchFile:
            pass

        self.assertEqual([], rst)

        th.join()

    def test_wait_ignores_wall_clock_steps(self):
        # A wall clock step, such as an NTP correction, must not end a wait early. This wall clock moves an hour
        # forward on every read.
        hours = itertools.count(step=3600)
        clock = types.SimpleNamespace(time=lambda: next(hours), monotonic=time.monotonic, sleep=time.sleep)

        def _append():
            time.sleep(0.1)
            append_lines(self.fn, ["a"])

        th = k3thread.daemon(_append)

        rst = []
        with mock.patch.object(k3cat.cat, "time", clock), self.assertRaises(k3cat.NoData):
            rst.extend(k3cat.Cat(self.fn, strip=True).iterate(timeout=0.5))

        th.join()

        self.assertEqual(["a"], rst)

    @unittest.skipIf(os.geteuid() == 0, "root opens a file without read permission")
    def test_open_error_other_than_missing_file(self):
        # Only a missing file is waited for. Waiting cannot fix other errors, and NoSuchFile would hide them.
        append_lines(self.fn, ["a"])
        os.chmod(self.fn, 0)

        with self.assertRaises(PermissionError):
            list(k3cat.Cat(self.fn, strip=True).iterate(timeout=0))

    def test_wait_for_data(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        rst = []

        append_lines(self.fn, expected)

        def _append():
            for _ in range(5):
                time.sleep(0.1)
                append_lines(self.fn, expected)
            dd("appended")

        th = k3thread.daemon(_append)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0.3))

            self.fail("expect NoData to raise")
        except k3cat.NoData:
            pass

        th.join()
        self.assertEqual(expected * 6, rst)

    def test_wait_for_data_timeout(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        rst = []

        append_lines(self.fn, expected)
        dd("appended 1")

        def _append():
            time.sleep(2)
            append_lines(self.fn, expected)
            dd("appended")

        th = k3thread.daemon(_append)

        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0.1))

            self.fail("expect NoData to raise")
        except k3cat.NoData:
            pass

        th.join()
        self.assertEqual(expected, rst)

    def test_exclusive(self):
        append_lines(self.fn, ["x"])

        # by default it is exclusive
        a = k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1)
        b = k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1)

        val = next(a)
        self.assertEqual("x", val)
        self.assertRaises(k3cat.LockTimeout, b.__next__)

        # non-exclusive still work
        # a has not yet quit, thus it has not yet written offset to stat file.
        c = k3cat.Cat(self.fn, strip=True, exclusive=False).iterate(timeout=0.1)
        val = next(c)
        self.assertEqual("x", val)

    def test_handler(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        append_lines(self.fn, expected)

        rst = []
        c = k3cat.Cat(self.fn, strip=True, handler=rst.append)
        c.cat(timeout=0)
        self.assertEqual(expected, rst)

        force_remove(c.stat_path())

        # handler is a list of callable
        exp = []
        for item in expected:
            exp.append(item)
            exp.append(item)

        rst = []
        force_remove(self.fn)
        append_lines(self.fn, expected)
        c = k3cat.Cat(self.fn, strip=True, handler=[rst.append, rst.append])
        c.cat(timeout=0)

        self.assertEqual(exp, rst)

    def test_file_end_handler(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        append_lines(self.fn, expected)

        rst = []

        def _end():
            rst.append("end")

        # file_end_handler in cat()
        c = k3cat.Cat(self.fn, strip=True, handler=rst.append, file_end_handler=_end)
        c.cat(timeout=0)
        self.assertEqual(expected + ["end"], rst)

        force_remove(c.stat_path())

        # file_end_handler in iterate()
        rst = []
        force_remove(self.fn)
        append_lines(self.fn, expected)
        cat = k3cat.Cat(self.fn, strip=True, file_end_handler=_end)
        rst.extend(cat.iterate(timeout=0))
        self.assertEqual(expected + ["end"], rst)

        force_remove(c.stat_path())

        # file_end_handler multi times
        rst = []
        force_remove(self.fn)
        append_lines(self.fn, expected)

        def _append():
            time.sleep(1)
            append_lines(self.fn, expected)

        th = k3thread.daemon(_append)

        try:
            cat = k3cat.Cat(self.fn, strip=True, file_end_handler=_end)
            rst.extend(cat.iterate(timeout=0.2))
        except k3cat.NoData:
            pass

        th.join()
        self.assertEqual((expected + ["end"]) * 2, rst)

    def test_cat(self):
        self.test_handler()

    def test_strip(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        append_lines(self.fn, expected)

        # by default do not strip
        cat = k3cat.Cat(self.fn)
        rst = list(cat.iterate(timeout=0))

        self.assertEqual([x + "\n" for x in expected], rst)

    def test_id(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        append_lines(self.fn, expected)

        force_remove(k3cat.Cat(self.fn, id="foo").stat_path())
        force_remove(k3cat.Cat(self.fn, id="bar").stat_path())

        # different id does not block each other even they cat a same file
        a = k3cat.Cat(self.fn, id="foo", strip=True).iterate(timeout=0)
        b = k3cat.Cat(self.fn, id="bar", strip=True).iterate(timeout=0)

        self.assertEqual(expected[0], next(a))
        self.assertEqual(expected[0], next(b))

    def test_config(self):
        expected = [
            "a" * 32,
            "b" * 32,
        ]
        append_lines(self.fn, expected)

        rc, out, err = k3proc.shell_script(
            pyt + " " + this_base + "/cat/cat_load_config.py " + self.fn,
        )

        dd(rc)
        dd(out)
        dd(err)

        self.assertEqual(0, rc)

        path = [
            "fsutil_cat_lock_",
            "cat_load_config.py",
        ] + os.path.realpath(self.fn)[1:].split(os.path.sep)
        path = "./" + "!".join(path)
        dd(path)

        self.assertTrue(os.path.isfile(path))

        force_remove(path)

    def test_default_seek(self):
        cases = (
            ("abc", {"default_seek": k3cat.SEEK_START}, ["abc"]),
            ("abc", {"default_seek": 0}, ["abc"]),
            ("abc", {"default_seek": 1}, ["bc"]),
            ("abc", {"default_seek": -2}, ["c"]),
            ("abc", {"default_seek": -100}, ["abc"]),
            ("abc", {"default_seek": k3cat.SEEK_END}, []),
            ("abc", {}, ["abc"]),
        )

        for file_content, kwargs, expected in cases:
            c = k3cat.Cat(self.fn)
            force_remove(c.stat_path())

            append_lines(self.fn, [file_content])

            rst = []
            try:
                kwargs["timeout"] = 0.1
                cat = k3cat.Cat(self.fn, strip=True)
                rst.extend(cat.iterate(**kwargs))
            except k3cat.NoData:
                pass

            self.assertEqual(expected, rst)

            force_remove(self.fn)

    def test_max_residual(self):
        c = k3cat.Cat(self.fn)
        force_remove(c.stat_path())

        append_lines(self.fn, ["123"])

        rst = []
        try:
            cat = k3cat.Cat(self.fn, strip=True)
            rst.extend(cat.iterate(timeout=0.1))
        except k3cat.NoData:
            pass

        self.assertEqual(["123"], rst)

        append_lines(self.fn, ["0" * 1000])

        rst = []
        try:
            cat = k3cat.Cat(self.fn, strip=False)
            rst.extend(cat.iterate(timeout=0.1, default_seek=-100))
        except k3cat.NoData:
            pass

        self.assertEqual(["0" * 99 + "\n"], rst)

    def test_reset_stat(self):
        cat = k3cat.Cat(self.fn, strip=True)
        force_remove(cat.stat_path())

        append_lines(self.fn, ["123"])

        rst = []
        try:
            rst.extend(cat.iterate(timeout=0.1))
        except k3cat.NoData:
            pass

        self.assertEqual(["123"], rst)

        append_lines(self.fn, ["456"])

        rst = []
        try:
            rst.extend(cat.iterate(timeout=0.1))
        except k3cat.NoData:
            pass

        self.assertEqual(["456"], rst)

        cat.reset_stat()

        rst = []
        try:
            rst.extend(cat.iterate(timeout=0.1))
        except k3cat.NoData:
            pass

        self.assertEqual(["123", "456"], rst)


def force_remove(fn):
    try:
        os.rmdir(fn)
    except OSError:
        pass

    try:
        os.unlink(fn)
    except OSError:
        pass


def append_lines(fn, lines):
    with open(fn, "a") as f:
        f.writelines(line + "\n" for line in lines)
        f.flush()
        os.fsync(f.fileno())


def append_bytes(fn, *strings):
    with open(fn, "a") as f:
        f.writelines(strings)
        f.flush()
        os.fsync(f.fileno())
