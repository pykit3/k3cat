#!/usr/bin/env python
# coding: utf-8

import os
import sys
import time
import unittest

import k3cat
import k3fs
import k3proc
import k3thread
import k3ut

dd = k3ut.dd

# xx/pykit/fsutil/test/
this_base = os.path.dirname(__file__)

pyt = sys.executable


class TestCat(unittest.TestCase):
    fn = "/tmp/pykit-cat-test-content"

    def setUp(self):
        force_remove(self.fn)
        c = k3cat.Cat(self.fn)
        force_remove(c.stat_path())

    def tearDown(self):
        force_remove(self.fn)
        c = k3cat.Cat(self.fn)
        force_remove(c.stat_path())

    def test_entire_file(self):
        expected = [
            "a",
            "bcd",
        ]

        append_lines(self.fn, expected)

        rst = []
        for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0):
            rst.append(line)

        self.assertEqual(expected, rst)

    def test_entire_large_file(self):
        expected = [
            "a" * 1024 * 32,
            "b" * 1024 * 32,
        ] * 1024

        append_lines(self.fn, expected)

        dd(os.system("ls -l /tmp/pykit*"))

        rst = []
        for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0):
            rst.append(line)

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

        rst = []
        for val in cat_handle.iterate(timeout=0):
            rst.append(val)
        self.assertEqual(expected, rst)

        # stat file was removed
        k3fs.remove(cat_handle.stat_path())
        for val in cat_handle.iterate(timeout=0):
            rst.append(val)
        self.assertEqual(expected * 2, rst)

        # stat file was damaged
        k3fs.fwrite(cat_handle.stat_path(), "{]")
        for val in cat_handle.iterate(timeout=0):
            rst.append(val)
        self.assertEqual(expected * 3, rst)

    def test_data_chucked(self):
        expected = ["a" * 32]
        new_data = ["b" * 32]
        chucked = ["c" * 31]

        cat_handle = k3cat.Cat(self.fn, strip=True)
        rst = []

        append_lines(self.fn, expected)
        for line in cat_handle.iterate(timeout=0):
            rst.append(line)
        self.assertEqual(expected, rst)

        # file was refreshed
        os.rename(self.fn, self.fn + "_old")
        append_lines(self.fn, new_data)
        k3fs.remove(self.fn + "_old")
        for line in cat_handle.iterate(timeout=0):
            rst.append(line)
        self.assertEqual(expected + new_data, rst)

        # file was chucked
        k3fs.fwrite(self.fn, chucked[0])
        for line in cat_handle.iterate(timeout=0):
            rst.append(line)
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

            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0):
                rst.append(line)

            self.assertEqual(expected * i, rst)

    def test_file_change(self):
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
                time.sleep(0.6)

        th = k3thread.daemon(_override)

        try:
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=2):
                rst.append(line)
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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=2):
                rst.append(line)
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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.4):
                rst.append(line)
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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1):
                rst.append(line)

            self.fail("expect NoSuchFile to raise")
        except k3cat.NoSuchFile:
            pass

        self.assertEqual([], rst)

        th.join()

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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.3):
                rst.append(line)

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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1):
                rst.append(line)

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
        for line in k3cat.Cat(self.fn, strip=True, file_end_handler=_end).iterate(timeout=0):
            rst.append(line)
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
            for line in k3cat.Cat(self.fn, strip=True, file_end_handler=_end).iterate(timeout=0.2):
                rst.append(line)
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
        rst = []
        for line in k3cat.Cat(self.fn).iterate(timeout=0):
            rst.append(line)

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
                for line in k3cat.Cat(self.fn, strip=True).iterate(**kwargs):
                    rst.append(line)
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
            for line in k3cat.Cat(self.fn, strip=True).iterate(timeout=0.1):
                rst.append(line)
        except k3cat.NoData:
            pass

        self.assertEqual(["123"], rst)

        append_lines(self.fn, ["0" * 1000])

        rst = []
        try:
            for line in k3cat.Cat(self.fn, strip=False).iterate(timeout=0.1, default_seek=-100):
                rst.append(line)
        except k3cat.NoData:
            pass

        self.assertEqual(["0" * 99 + "\n"], rst)

    def test_reset_stat(self):
        cat = k3cat.Cat(self.fn, strip=True)
        force_remove(cat.stat_path())

        append_lines(self.fn, ["123"])

        rst = []
        try:
            for line in cat.iterate(timeout=0.1):
                rst.append(line)
        except k3cat.NoData:
            pass

        self.assertEqual(["123"], rst)

        append_lines(self.fn, ["456"])

        rst = []
        try:
            for line in cat.iterate(timeout=0.1):
                rst.append(line)
        except k3cat.NoData:
            pass

        self.assertEqual(["456"], rst)

        cat.reset_stat()

        rst = []
        try:
            for line in cat.iterate(timeout=0.1):
                rst.append(line)
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
        for line in lines:
            f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_bytes(fn, *strings):
    with open(fn, "a") as f:
        for s in strings:
            f.write(s)
        f.flush()
        os.fsync(f.fileno())
