#!/usr/bin/env python3
"""
SQRay Automated Test Suite
==========================
Comprehensive zero-dependency unit and integration tests for SQRay.
Uses only the Python standard library (unittest, tempfile, os, sys, struct, io, re).

Run with:
    python -m unittest test_sqray.py -v
    or
    python test_sqray.py
"""

import unittest
import os
import sys
import struct
import io
import re

# Import core SQRay components from sqray.py
import sqray

def strip_ansi(text: str) -> str:
    """Strips ANSI/VT100 escape sequences for robust assertion testing."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def setUpModule():
    """Ensure sample test fixtures exist for automated test execution."""
    if not (os.path.exists("demo.db") and os.path.exists("btree.db") and os.path.exists("wal.db-wal")):
        try:
            import generate_samples
            generate_samples.create_sample_simple("demo.db")
            generate_samples.create_sample_btree_deep("btree.db")
            generate_samples.create_sample_wal("wal.db")
        except Exception:
            pass


class TestVarintDecoder(unittest.TestCase):
    """Tests for SQLite 1-9 byte variable-length integer decoding."""

    def test_single_byte_varint(self):
        # Single byte varints (< 128)
        buf = bytes([0x00, 0x01, 0x7F])
        val, consumed = sqray.read_varint(buf, 0)
        self.assertEqual(val, 0)
        self.assertEqual(consumed, 1)

        val, consumed = sqray.read_varint(buf, 1)
        self.assertEqual(val, 1)
        self.assertEqual(consumed, 1)

        val, consumed = sqray.read_varint(buf, 2)
        self.assertEqual(val, 127)
        self.assertEqual(consumed, 1)

    def test_two_byte_varint(self):
        # 0x81, 0x00 -> 128
        buf = bytes([0x81, 0x00])
        val, consumed = sqray.read_varint(buf, 0)
        self.assertEqual(val, 128)
        self.assertEqual(consumed, 2)

        # 0x81, 0x01 -> 129
        buf = bytes([0x81, 0x01])
        val, consumed = sqray.read_varint(buf, 0)
        self.assertEqual(val, 129)
        self.assertEqual(consumed, 2)

    def test_nine_byte_varint(self):
        # 9-byte max varint: 8 bytes with 0xFF + 1 byte with 0xFF
        buf = bytes([0xFF] * 9)
        val, consumed = sqray.read_varint(buf, 0)
        self.assertEqual(consumed, 9)
        self.assertEqual(val, 0xFFFFFFFFFFFFFFFF)


class TestRecordDecoder(unittest.TestCase):
    """Tests for SQLite Record Header and Serial Type decoding."""

    def test_decode_record_payload(self):
        # Construct record:
        # header_size = 4 (varint 0x04)
        # col1: serial type 1 (8-bit int 42 -> 0x2A)
        # col2: serial type 9 (const 1)
        # col3: serial type 23 (text 'Hello', 5 bytes -> (5*2)+13 = 23 -> 0x17)
        # Header bytes: [0x04, 0x01, 0x09, 0x17]
        # Data bytes: [0x2A, b'Hello']
        payload = bytes([0x04, 0x01, 0x09, 0x17, 0x2A]) + b"Hello"
        values = sqray.SQLiteRecord.decode(payload)
        self.assertEqual(values, [42, 1, "Hello"])

    def test_decode_record_with_floats_and_nulls(self):
        # header_size = 3 (varint 0x03)
        # col1: serial type 0 (NULL)
        # col2: serial type 7 (64-bit float 3.14159)
        # Header bytes: [0x03, 0x00, 0x07]
        float_bytes = struct.pack(">d", 3.14159)
        payload = bytes([0x03, 0x00, 0x07]) + float_bytes
        values = sqray.SQLiteRecord.decode(payload)
        self.assertEqual(len(values), 2)
        self.assertIsNone(values[0])
        self.assertAlmostEqual(values[1], 3.14159, places=5)


class TestSQLiteHeaderParsing(unittest.TestCase):
    """Tests parsing the 100-byte SQLite database header."""

    def test_header_validation_demo_db(self):
        if not os.path.exists("demo.db"):
            self.skipTest("demo.db not found")
        
        with sqray.RawSQLiteReader("demo.db") as reader:
            header = reader.header
            self.assertEqual(header.magic, b"SQLite format 3\x00")
            self.assertEqual(header.page_size, 4096)
            self.assertEqual(header.computed_page_count, 2)
            self.assertEqual(header.text_encoding, 1) # UTF-8
            self.assertEqual(header.user_version, 42)
            self.assertEqual(header.application_id, 0x53515259)


class TestBTreeWalker(unittest.TestCase):
    """Tests recursive B-Tree parsing on multi-level and single-level trees."""

    def test_demo_db_schema(self):
        if not os.path.exists("demo.db"):
            self.skipTest("demo.db not found")
        
        with sqray.RawSQLiteReader("demo.db") as reader:
            schema_objs = reader.get_schema()
            table_names = [obj.name for obj in schema_objs if obj.entry_type == "table"]
            self.assertIn("items", table_names)

    def test_btree_multi_page_traversal(self):
        if not os.path.exists("btree.db"):
            self.skipTest("btree.db not found")
        
        with sqray.RawSQLiteReader("btree.db") as reader:
            root_page = reader.get_page(2)
            self.assertEqual(root_page.page_num, 2)
            self.assertEqual(root_page.page_type, sqray.PageType.INTERIOR_TABLE)
            self.assertGreater(len(root_page.cells), 0)


class TestWALForensics(unittest.TestCase):
    """Tests Write-Ahead Log parsing."""

    def test_wal_parsing(self):
        if not os.path.exists("wal.db-wal"):
            self.skipTest("wal.db-wal not found")
        
        reader = sqray.WALReader("wal.db-wal")
        self.assertIsNotNone(reader.header)
        self.assertEqual(reader.header.magic, 0x377F0682)
        self.assertEqual(reader.header.page_size, 4096)
        self.assertEqual(len(reader.frames), 4)
        
        # Verify commit boundaries
        commit_frames = [f for f in reader.frames if f.is_commit]
        self.assertEqual(len(commit_frames), 2)


class TestCLIExecution(unittest.TestCase):
    """Tests end-to-end CLI execution and output captures."""

    def test_cli_inspect_demo(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.inspect("demo.db")
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("DATABASE HEADER & METADATA SUMMARY", output)
            self.assertIn("items", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_page_analysis(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.page("demo.db", page_num=2)
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("PAGE 2 STRUCTURAL BREAKDOWN", output)
            self.assertIn("Cell Pointer Array", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_tree_analysis(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.tree("demo.db")
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("B-Tree Hierarchy", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_map_analysis(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.map_pages("demo.db")
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("PAGE ALLOCATION GRID MAP", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_dump_analysis(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.dump_table("demo.db", "items", limit=5)
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("PURE BINARY ROW EXTRACTION: items", output)
            self.assertIn("Vintage Camera", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_wal_analysis(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout_capture
            sqray.SQRayCLI.wal("wal.db")
            output = strip_ansi(stdout_capture.getvalue())
            self.assertIn("WAL (WRITE-AHEAD LOG) HEADER SUMMARY", output)
            self.assertIn("UN-CHECKPOINTED TRANSACTION FRAMES", output)
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
