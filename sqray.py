#!/usr/bin/env python3
"""
SQRay - Zero-Dependency Terminal SQLite Deep-Inspection & B-Tree Visualizer
==========================================================================
A pure-Python, zero-dependency systems utility to parse, inspect, map,
and visualize raw SQLite database files (.sqlite, .db) and Write-Ahead Logs (-wal)
byte-by-byte without using any database drivers or external packages.

Strictly Standard Library: sys, struct, os, pathlib, typing, enum, math, time.
"""

import sys
import os
import struct
import math
import time
from typing import List, Dict, Tuple, Optional, Any, Set
from dataclasses import dataclass
from enum import IntEnum

# Ensure UTF-8 output encoding across Windows, Linux, and macOS
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==============================================================================
# 1. ANSI STYLING & TERMINAL ENGINE
# ==============================================================================

class Styler:
    """Terminal styling, 24-bit/256-color support, box-drawing characters."""
    # Check if stdout is a TTY and supports ANSI colors
    ENABLED = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    # On Windows 10+, enable virtual terminal processing if available
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

    # Core Palette
    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""
    ITALIC = "\033[3m" if ENABLED else ""
    UNDERLINE = "\033[4m" if ENABLED else ""

    # Vibrant Colors
    CYAN = "\033[38;5;51m" if ENABLED else ""
    BLUE = "\033[38;5;75m" if ENABLED else ""
    DEEP_BLUE = "\033[38;5;33m" if ENABLED else ""
    PURPLE = "\033[38;5;141m" if ENABLED else ""
    MAGENTA = "\033[38;5;201m" if ENABLED else ""
    GREEN = "\033[38;5;48m" if ENABLED else ""
    EMERALD = "\033[38;5;42m" if ENABLED else ""
    YELLOW = "\033[38;5;220m" if ENABLED else ""
    AMBER = "\033[38;5;214m" if ENABLED else ""
    ORANGE = "\033[38;5;208m" if ENABLED else ""
    RED = "\033[38;5;196m" if ENABLED else ""
    CORAL = "\033[38;5;203m" if ENABLED else ""
    GRAY = "\033[38;5;245m" if ENABLED else ""
    DARK_GRAY = "\033[38;5;238m" if ENABLED else ""
    WHITE = "\033[38;5;255m" if ENABLED else ""

    # Backgrounds
    BG_DARK = "\033[48;5;235m" if ENABLED else ""
    BG_CYAN = "\033[48;5;30m" if ENABLED else ""
    BG_BLUE = "\033[48;5;24m" if ENABLED else ""
    BG_PURPLE = "\033[48;5;55m" if ENABLED else ""
    BG_MAGENTA = "\033[48;5;127m" if ENABLED else ""
    BG_AMBER = "\033[48;5;130m" if ENABLED else ""
    BG_GREEN = "\033[48;5;28m" if ENABLED else ""
    BG_RED = "\033[48;5;88m" if ENABLED else ""

    @classmethod
    def clear_screen(cls):
        """Clears the terminal screen and scrollback buffer, positioning the cursor at top-left."""
        if cls.ENABLED:
            # ANSI: clear screen (\033[2J), clear scrollback buffer (\033[3J), cursor to (1,1) (\033[H)
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()
        else:
            os.system("cls" if os.name == "nt" else "clear")

    @classmethod
    def badge(cls, text: str, bg_color: str, fg_color: str = WHITE) -> str:
        if not cls.ENABLED:
            return f"[{text}]"
        return f"{bg_color}{fg_color}{cls.BOLD} {text} {cls.RESET}"

    @classmethod
    def banner(cls) -> str:
        b = f"""
{cls.CYAN}{cls.BOLD}  ███████╗ ██████╗ ██████╗  █████╗ ██╗   ██╗
  ██╔════╝██╔═══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
  ███████╗██║   ██║██████╔╝███████║ ╚████╔╝ 
  ╚════██║██║▄▄ ██║██╔══██╗██╔══██║  ╚██╔╝  
  ███████║╚██████╔╝██║  ██║██║  ██║   ██║   
  ╚══════╝ ╚══▀▀═╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   {cls.RESET}
  {cls.AMBER}⚡ Zero-Dependency SQLite Deep-Inspection & B-Tree Visualizer{cls.RESET}
"""
        return b


# ==============================================================================
# 2. BINARY UNPACKING PRIMITIVES & VARINT DECODERS
# ==============================================================================

def read_u8(buf: bytes, offset: int) -> int:
    return buf[offset]

def read_u16(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">H", buf, offset)[0]

def read_u24(buf: bytes, offset: int) -> int:
    b0, b1, b2 = struct.unpack_from(">BBB", buf, offset)
    return (b0 << 16) | (b1 << 8) | b2

def read_u32(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">I", buf, offset)[0]

def read_i8(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">b", buf, offset)[0]

def read_i16(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">h", buf, offset)[0]

def read_i24(buf: bytes, offset: int) -> int:
    u = read_u24(buf, offset)
    if u & 0x800000:
        return u - 0x1000000
    return u

def read_i32(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">i", buf, offset)[0]

def read_i48(buf: bytes, offset: int) -> int:
    hi, lo = struct.unpack_from(">HI", buf, offset)
    val = (hi << 32) | lo
    if val & 0x800000000000:
        return val - 0x1000000000000
    return val

def read_i64(buf: bytes, offset: int) -> int:
    return struct.unpack_from(">q", buf, offset)[0]

def read_f64(buf: bytes, offset: int) -> float:
    return struct.unpack_from(">d", buf, offset)[0]

def read_varint(buf: bytes, offset: int = 0) -> Tuple[int, int]:
    """
    Decodes a SQLite variable-length integer (1 to 9 bytes).
    Returns (decoded_value, bytes_consumed).
    """
    val = 0
    buf_len = len(buf)
    for i in range(8):
        if offset + i >= buf_len:
            return val, i
        b = buf[offset + i]
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i + 1
    # 9th byte uses all 8 bits
    if offset + 8 < buf_len:
        b = buf[offset + 8]
        val = (val << 8) | b
        return val, 9
    return val, 8


# ==============================================================================
# 3. SQLITE 100-BYTE DATABASE HEADER SPECIFICATION
# ==============================================================================

@dataclass
class SQLiteHeader:
    magic: bytes
    page_size: int
    write_version: int
    read_version: int
    reserved_bytes: int
    max_payload_fraction: int
    min_payload_fraction: int
    leaf_payload_fraction: int
    file_change_counter: int
    in_header_page_count: int
    freelist_trunk_page: int
    total_freelist_pages: int
    schema_cookie: int
    schema_format: int
    default_cache_size: int
    largest_root_page: int
    text_encoding: int
    user_version: int
    incremental_vacuum: int
    application_id: int
    version_valid_for: int
    sqlite_version_num: int
    file_size_bytes: int

    @property
    def computed_page_count(self) -> int:
        return self.file_size_bytes // self.page_size if self.page_size else 0

    @property
    def effective_page_count(self) -> int:
        return self.in_header_page_count if self.in_header_page_count > 0 else self.computed_page_count

    @property
    def usable_page_size(self) -> int:
        return self.page_size - self.reserved_bytes

    @property
    def encoding_str(self) -> str:
        enc_map = {1: "UTF-8", 2: "UTF-16le", 3: "UTF-16be"}
        return enc_map.get(self.text_encoding, f"Unknown ({self.text_encoding})")

    @property
    def version_str(self) -> str:
        v = self.sqlite_version_num
        major = v // 1000000
        minor = (v % 1000000) // 1000
        patch = v % 1000
        return f"{major}.{minor}.{patch}"

    @property
    def app_id_str(self) -> str:
        if self.application_id == 0:
            return "0x00000000 (None)"
        # Try converting to 4 ASCII chars
        try:
            ascii_repr = struct.pack(">I", self.application_id).decode("ascii")
            if ascii_repr.isprintable():
                return f"0x{self.application_id:08X} ('{ascii_repr}')"
        except Exception:
            pass
        return f"0x{self.application_id:08X}"

    @classmethod
    def parse(cls, header_bytes: bytes, file_size: int) -> "SQLiteHeader":
        if len(header_bytes) < 100:
            raise ValueError(f"File too small for SQLite header ({len(header_bytes)} bytes, expected >= 100)")
        
        magic = header_bytes[0:16]
        if magic != b"SQLite format 3\x00":
            raise ValueError(f"Invalid SQLite magic header: {magic!r}")

        raw_page_size = read_u16(header_bytes, 16)
        # In SQLite 3, value 1 in header means 65536 bytes
        page_size = 65536 if raw_page_size == 1 else raw_page_size
        if page_size < 512 or (page_size & (page_size - 1)) != 0:
            raise ValueError(f"Invalid page size: {page_size} (must be power of 2 between 512 and 65536)")

        write_ver = read_u8(header_bytes, 18)
        read_ver = read_u8(header_bytes, 19)
        reserved = read_u8(header_bytes, 20)
        max_p_frac = read_u8(header_bytes, 21)
        min_p_frac = read_u8(header_bytes, 22)
        leaf_p_frac = read_u8(header_bytes, 23)

        change_counter = read_u32(header_bytes, 24)
        in_header_page_count = read_u32(header_bytes, 28)
        freelist_trunk = read_u32(header_bytes, 32)
        freelist_count = read_u32(header_bytes, 36)
        schema_cookie = read_u32(header_bytes, 40)
        schema_format = read_u32(header_bytes, 44)
        default_cache = read_u32(header_bytes, 48)
        largest_root = read_u32(header_bytes, 52)
        text_enc = read_u32(header_bytes, 56)
        user_ver = read_u32(header_bytes, 60)
        inc_vacuum = read_u32(header_bytes, 64)
        app_id = read_u32(header_bytes, 68)
        valid_for = read_u32(header_bytes, 92)
        sqlite_ver = read_u32(header_bytes, 96)

        return cls(
            magic=magic,
            page_size=page_size,
            write_version=write_ver,
            read_version=read_ver,
            reserved_bytes=reserved,
            max_payload_fraction=max_p_frac,
            min_payload_fraction=min_p_frac,
            leaf_payload_fraction=leaf_p_frac,
            file_change_counter=change_counter,
            in_header_page_count=in_header_page_count,
            freelist_trunk_page=freelist_trunk,
            total_freelist_pages=freelist_count,
            schema_cookie=schema_cookie,
            schema_format=schema_format,
            default_cache_size=default_cache,
            largest_root_page=largest_root,
            text_encoding=text_enc,
            user_version=user_ver,
            incremental_vacuum=inc_vacuum,
            application_id=app_id,
            version_valid_for=valid_for,
            sqlite_version_num=sqlite_ver,
            file_size_bytes=file_size
        )


# ==============================================================================
# 4. B-TREE PAGE & CELL DECODING
# ==============================================================================

class PageType(IntEnum):
    INTERIOR_INDEX = 0x02
    INTERIOR_TABLE = 0x05
    LEAF_INDEX = 0x0A
    LEAF_TABLE = 0x0D
    UNKNOWN = 0x00

    @property
    def display_name(self) -> str:
        names = {
            PageType.INTERIOR_INDEX: "Interior Index Page",
            PageType.INTERIOR_TABLE: "Interior Table Page",
            PageType.LEAF_INDEX: "Leaf Index Page",
            PageType.LEAF_TABLE: "Leaf Table Page",
            PageType.UNKNOWN: "Unknown / Non-BTree Page"
        }
        return names.get(self, "Unknown Page")

    @property
    def short_tag(self) -> str:
        tags = {
            PageType.INTERIOR_INDEX: "IDX-INT",
            PageType.INTERIOR_TABLE: "TBL-INT",
            PageType.LEAF_INDEX: "IDX-LEAF",
            PageType.LEAF_TABLE: "TBL-LEAF",
            PageType.UNKNOWN: "RAW/FREE"
        }
        return tags.get(self, "????")


@dataclass
class SQLiteCell:
    cell_index: int
    offset: int
    length: int
    payload_size: int = 0
    rowid: Optional[int] = None
    left_child_page: Optional[int] = None
    payload: bytes = b""
    overflow_page: Optional[int] = None
    decoded_record: Optional[List[Any]] = None


@dataclass
class BTreePage:
    page_num: int
    page_size: int
    page_type: PageType
    raw_data: bytes
    header_offset: int
    first_freeblock: int
    cell_count: int
    cell_content_offset: int
    fragmented_free_bytes: int
    right_child_page: Optional[int]
    cell_pointers: List[int]
    cells: List[SQLiteCell]

    @property
    def is_leaf(self) -> bool:
        return self.page_type in (PageType.LEAF_TABLE, PageType.LEAF_INDEX)

    @property
    def is_table(self) -> bool:
        return self.page_type in (PageType.INTERIOR_TABLE, PageType.LEAF_TABLE)

    @property
    def is_index(self) -> bool:
        return self.page_type in (PageType.INTERIOR_INDEX, PageType.LEAF_INDEX)

    @classmethod
    def parse(cls, page_num: int, page_data: bytes, page_size: int, reserved_bytes: int = 0) -> "BTreePage":
        header_offset = 100 if page_num == 1 else 0
        if len(page_data) < header_offset + 8:
            return cls(
                page_num=page_num,
                page_size=page_size,
                page_type=PageType.UNKNOWN,
                raw_data=page_data,
                header_offset=header_offset,
                first_freeblock=0,
                cell_count=0,
                cell_content_offset=0,
                fragmented_free_bytes=0,
                right_child_page=None,
                cell_pointers=[],
                cells=[]
            )

        flag_byte = read_u8(page_data, header_offset)
        try:
            page_type = PageType(flag_byte)
        except ValueError:
            page_type = PageType.UNKNOWN

        if page_type == PageType.UNKNOWN:
            return cls(
                page_num=page_num,
                page_size=page_size,
                page_type=PageType.UNKNOWN,
                raw_data=page_data,
                header_offset=header_offset,
                first_freeblock=0,
                cell_count=0,
                cell_content_offset=0,
                fragmented_free_bytes=0,
                right_child_page=None,
                cell_pointers=[],
                cells=[]
            )

        first_freeblock = read_u16(page_data, header_offset + 1)
        cell_count = read_u16(page_data, header_offset + 3)
        raw_cell_content = read_u16(page_data, header_offset + 5)
        cell_content_offset = page_size if raw_cell_content == 0 else raw_cell_content
        frag_bytes = read_u8(page_data, header_offset + 7)

        is_interior = page_type in (PageType.INTERIOR_TABLE, PageType.INTERIOR_INDEX)
        header_size = 12 if is_interior else 8

        right_child: Optional[int] = None
        if is_interior and len(page_data) >= header_offset + 12:
            right_child = read_u32(page_data, header_offset + 8)

        # Parse Cell Pointer Array
        ptr_array_offset = header_offset + header_size
        cell_pointers = []
        for i in range(cell_count):
            p_offset = ptr_array_offset + (i * 2)
            if p_offset + 2 <= len(page_data):
                cell_pointers.append(read_u16(page_data, p_offset))

        # Parse individual cells
        cells = []
        usable_size = page_size - reserved_bytes
        for idx, c_off in enumerate(cell_pointers):
            if c_off >= len(page_data) or c_off < 0:
                continue

            cell = cls._parse_single_cell(
                page_data=page_data,
                c_off=c_off,
                idx=idx,
                page_type=page_type,
                usable_size=usable_size
            )
            cells.append(cell)

        return cls(
            page_num=page_num,
            page_size=page_size,
            page_type=page_type,
            raw_data=page_data,
            header_offset=header_offset,
            first_freeblock=first_freeblock,
            cell_count=cell_count,
            cell_content_offset=cell_content_offset,
            fragmented_free_bytes=frag_bytes,
            right_child_page=right_child,
            cell_pointers=cell_pointers,
            cells=cells
        )

    @classmethod
    def _parse_single_cell(
        cls,
        page_data: bytes,
        c_off: int,
        idx: int,
        page_type: PageType,
        usable_size: int
    ) -> SQLiteCell:
        curr = c_off
        left_child: Optional[int] = None
        rowid: Optional[int] = None
        payload_size = 0
        payload_bytes = b""
        overflow_page: Optional[int] = None

        if page_type == PageType.LEAF_TABLE:
            # Varint: Payload size
            psize, n1 = read_varint(page_data, curr)
            curr += n1
            payload_size = psize

            # Varint: Row ID (integer primary key)
            rid, n2 = read_varint(page_data, curr)
            curr += n2
            rowid = rid

            # SQLite local payload calculation:
            # U = usable_size
            # X = U - 35
            # M = ((U - 12) * 32 // 255) - 23
            # If P <= X, local = P. If P > X: let K = M + ((P - M) % (U - 4)). If K <= X, local = K else local = M.
            u = usable_size
            x = u - 35
            m = ((u - 12) * 32 // 255) - 23
            if payload_size <= x:
                local_size = payload_size
            else:
                k = m + ((payload_size - m) % (u - 4))
                local_size = k if k <= x else m

            payload_bytes = page_data[curr: curr + local_size]
            curr += local_size
            if local_size < payload_size and curr + 4 <= len(page_data):
                overflow_page = read_u32(page_data, curr)
                curr += 4

        elif page_type == PageType.INTERIOR_TABLE:
            # 4-byte left child page
            if curr + 4 <= len(page_data):
                left_child = read_u32(page_data, curr)
                curr += 4
            # Varint: Row ID
            rid, n = read_varint(page_data, curr)
            curr += n
            rowid = rid

        elif page_type == PageType.LEAF_INDEX:
            # Varint: Payload size
            psize, n1 = read_varint(page_data, curr)
            curr += n1
            payload_size = psize

            u = usable_size
            x = ((u - 12) * 64 // 255) - 23
            m = ((u - 12) * 32 // 255) - 23
            if payload_size <= x:
                local_size = payload_size
            else:
                k = m + ((payload_size - m) % (u - 4))
                local_size = k if k <= x else m

            payload_bytes = page_data[curr: curr + local_size]
            curr += local_size
            if local_size < payload_size and curr + 4 <= len(page_data):
                overflow_page = read_u32(page_data, curr)
                curr += 4

        elif page_type == PageType.INTERIOR_INDEX:
            # 4-byte left child page
            if curr + 4 <= len(page_data):
                left_child = read_u32(page_data, curr)
                curr += 4
            # Varint: Payload size
            psize, n1 = read_varint(page_data, curr)
            curr += n1
            payload_size = psize

            u = usable_size
            x = ((u - 12) * 64 // 255) - 23
            m = ((u - 12) * 32 // 255) - 23
            if payload_size <= x:
                local_size = payload_size
            else:
                k = m + ((payload_size - m) % (u - 4))
                local_size = k if k <= x else m

            payload_bytes = page_data[curr: curr + local_size]
            curr += local_size
            if local_size < payload_size and curr + 4 <= len(page_data):
                overflow_page = read_u32(page_data, curr)
                curr += 4

        cell_len = max(curr - c_off, 1)

        # Attempt decoding SQLite record if payload present
        decoded: Optional[List[Any]] = None
        if payload_bytes:
            try:
                decoded = SQLiteRecord.decode(payload_bytes)
            except Exception:
                decoded = None

        return SQLiteCell(
            cell_index=idx,
            offset=c_off,
            length=cell_len,
            payload_size=payload_size,
            rowid=rowid,
            left_child_page=left_child,
            payload=payload_bytes,
            overflow_page=overflow_page,
            decoded_record=decoded
        )


# ==============================================================================
# 5. SQLITE RECORD FORMAT & SERIAL TYPE DECODER
# ==============================================================================

class SQLiteRecord:
    """Decodes SQLite binary record payload and serial types into Python values."""
    @staticmethod
    def decode(payload: bytes) -> List[Any]:
        if not payload:
            return []
        
        # Header size varint
        header_size, n = read_varint(payload, 0)
        if header_size > len(payload) or header_size < n:
            return []

        # Read serial types from header
        serial_types = []
        curr = n
        while curr < header_size:
            stype, sn = read_varint(payload, curr)
            serial_types.append(stype)
            curr += sn

        # Decode data values
        data_cursor = header_size
        values = []
        for stype in serial_types:
            if stype == 0:
                values.append(None)
            elif stype == 1:
                # 8-bit int
                if data_cursor < len(payload):
                    values.append(read_i8(payload, data_cursor))
                    data_cursor += 1
                else:
                    values.append(None)
            elif stype == 2:
                # 16-bit int
                if data_cursor + 2 <= len(payload):
                    values.append(read_i16(payload, data_cursor))
                    data_cursor += 2
                else:
                    values.append(None)
            elif stype == 3:
                # 24-bit int
                if data_cursor + 3 <= len(payload):
                    values.append(read_i24(payload, data_cursor))
                    data_cursor += 3
                else:
                    values.append(None)
            elif stype == 4:
                # 32-bit int
                if data_cursor + 4 <= len(payload):
                    values.append(read_i32(payload, data_cursor))
                    data_cursor += 4
                else:
                    values.append(None)
            elif stype == 5:
                # 48-bit int
                if data_cursor + 6 <= len(payload):
                    values.append(read_i48(payload, data_cursor))
                    data_cursor += 6
                else:
                    values.append(None)
            elif stype == 6:
                # 64-bit int
                if data_cursor + 8 <= len(payload):
                    values.append(read_i64(payload, data_cursor))
                    data_cursor += 8
                else:
                    values.append(None)
            elif stype == 7:
                # 64-bit IEEE float
                if data_cursor + 8 <= len(payload):
                    values.append(read_f64(payload, data_cursor))
                    data_cursor += 8
                else:
                    values.append(None)
            elif stype == 8:
                values.append(0)
            elif stype == 9:
                values.append(1)
            elif stype in (10, 11):
                values.append(f"<internal_reserved_{stype}>")
            elif stype >= 12 and stype % 2 == 0:
                # BLOB of length (stype - 12) // 2
                blob_len = (stype - 12) // 2
                blob_val = payload[data_cursor: data_cursor + blob_len]
                values.append(blob_val)
                data_cursor += blob_len
            elif stype >= 13 and stype % 2 == 1:
                # TEXT of length (stype - 13) // 2
                text_len = (stype - 13) // 2
                text_bytes = payload[data_cursor: data_cursor + text_len]
                try:
                    text_val = text_bytes.decode("utf-8", errors="replace")
                except Exception:
                    text_val = str(text_bytes)
                values.append(text_val)
                data_cursor += text_len
            else:
                values.append(f"<unknown_stype_{stype}>")

        return values


# ==============================================================================
# 6. SCHEMA INTROSPECTION & DATABASE DRIVERLESS READER
# ==============================================================================

@dataclass
class SchemaEntry:
    entry_type: str # 'table', 'index', 'view', 'trigger'
    name: str
    tbl_name: str
    root_page: int
    sql: str


class RawSQLiteReader:
    """Driverless raw file binary reader and cache manager."""
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Database file not found: {filepath}")
        
        self.file_size = os.path.getsize(filepath)
        self._f = open(filepath, "rb")
        
        # Read header
        header_bytes = self._read_bytes(0, 100)
        self.header = SQLiteHeader.parse(header_bytes, self.file_size)
        self._page_cache: Dict[int, BTreePage] = {}

    def close(self):
        if self._f and not self._f.closed:
            self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _read_bytes(self, offset: int, length: int) -> bytes:
        self._f.seek(offset)
        return self._f.read(length)

    def read_page_raw(self, page_num: int) -> bytes:
        if page_num < 1:
            raise ValueError(f"Page numbers are 1-indexed (got {page_num})")
        offset = (page_num - 1) * self.header.page_size
        return self._read_bytes(offset, self.header.page_size)

    def get_page(self, page_num: int) -> BTreePage:
        if page_num in self._page_cache:
            return self._page_cache[page_num]
        
        raw_data = self.read_page_raw(page_num)
        page = BTreePage.parse(
            page_num=page_num,
            page_data=raw_data,
            page_size=self.header.page_size,
            reserved_bytes=self.header.reserved_bytes
        )
        self._page_cache[page_num] = page
        return page

    def get_schema(self) -> List[SchemaEntry]:
        """
        Parses sqlite_schema from Page 1 (and follows any interior child pages).
        sqlite_schema columns: (type, name, tbl_name, rootpage, sql)
        """
        entries: List[SchemaEntry] = []
        
        def traverse_schema_page(p_num: int):
            try:
                page = self.get_page(p_num)
            except Exception:
                return

            if page.page_type == PageType.LEAF_TABLE:
                for cell in page.cells:
                    rec = cell.decoded_record
                    if rec and len(rec) >= 5:
                        entry_type = str(rec[0] or "")
                        name = str(rec[1] or "")
                        tbl_name = str(rec[2] or "")
                        root_page = int(rec[3] or 0)
                        sql = str(rec[4] or "")
                        entries.append(SchemaEntry(entry_type, name, tbl_name, root_page, sql))
            elif page.page_type == PageType.INTERIOR_TABLE:
                for cell in page.cells:
                    if cell.left_child_page:
                        traverse_schema_page(cell.left_child_page)
                if page.right_child_page:
                    traverse_schema_page(page.right_child_page)

        traverse_schema_page(1)
        return entries


# ==============================================================================
# 7. WRITE-AHEAD LOG (WAL) PARSER
# ==============================================================================

@dataclass
class WALHeader:
    magic: int
    format_version: int
    page_size: int
    checkpoint_seq: int
    salt1: int
    salt2: int
    checksum1: int
    checksum2: int
    is_big_endian_checksum: bool

    @classmethod
    def parse(cls, header_bytes: bytes) -> "WALHeader":
        if len(header_bytes) < 32:
            raise ValueError("WAL header too short (< 32 bytes)")
        
        magic = read_u32(header_bytes, 0)
        # 0x377f0682 -> little-endian checksum, 0x377f0683 -> big-endian checksum
        if magic not in (0x377f0682, 0x377f0683):
            raise ValueError(f"Invalid WAL magic number: 0x{magic:08X} (expected 0x377F0682 or 0x377F0683)")
        
        version = read_u32(header_bytes, 4)
        page_size = read_u32(header_bytes, 8)
        seq = read_u32(header_bytes, 12)
        salt1 = read_u32(header_bytes, 16)
        salt2 = read_u32(header_bytes, 20)
        ck1 = read_u32(header_bytes, 24)
        ck2 = read_u32(header_bytes, 28)

        return cls(
            magic=magic,
            format_version=version,
            page_size=page_size,
            checkpoint_seq=seq,
            salt1=salt1,
            salt2=salt2,
            checksum1=ck1,
            checksum2=ck2,
            is_big_endian_checksum=(magic == 0x377f0683)
        )


@dataclass
class WALFrame:
    frame_index: int
    file_offset: int
    page_num: int
    db_size_pages_after_commit: int # 0 if not commit
    salt1: int
    salt2: int
    checksum1: int
    checksum2: int
    page_data: bytes

    @property
    def is_commit(self) -> bool:
        return self.db_size_pages_after_commit > 0


class WALReader:
    """Parses SQLite Write-Ahead Log (.sqlite-wal) frames."""
    def __init__(self, wal_filepath: str):
        self.filepath = wal_filepath
        if not os.path.exists(wal_filepath):
            raise FileNotFoundError(f"WAL file not found: {wal_filepath}")
        
        self.file_size = os.path.getsize(wal_filepath)
        with open(wal_filepath, "rb") as f:
            raw_header = f.read(32)
            self.header = WALHeader.parse(raw_header)
            self.frames: List[WALFrame] = []

            frame_size = 24 + self.header.page_size
            curr_offset = 32
            idx = 1

            while curr_offset + frame_size <= self.file_size:
                f.seek(curr_offset)
                f_hdr = f.read(24)
                f_page = f.read(self.header.page_size)

                page_num = read_u32(f_hdr, 0)
                db_size = read_u32(f_hdr, 4)
                s1 = read_u32(f_hdr, 8)
                s2 = read_u32(f_hdr, 12)
                c1 = read_u32(f_hdr, 16)
                c2 = read_u32(f_hdr, 20)

                frame = WALFrame(
                    frame_index=idx,
                    file_offset=curr_offset,
                    page_num=page_num,
                    db_size_pages_after_commit=db_size,
                    salt1=s1,
                    salt2=s2,
                    checksum1=c1,
                    checksum2=c2,
                    page_data=f_page
                )
                self.frames.append(frame)
                curr_offset += frame_size
                idx += 1


# ==============================================================================
# 8. COMMAND IMPLEMENTATIONS & VISUALIZERS
# ==============================================================================

class SQRayCLI:
    """CLI Command Execution and Formatting Dispatcher."""

    @staticmethod
    def inspect(filepath: str):
        """Displays database header, metrics, sanity checks, and schema listing."""
        print(Styler.banner())
        with RawSQLiteReader(filepath) as reader:
            h = reader.header
            st = Styler

            # Overview Card
            print(f"{st.BOLD}{st.CYAN}┌── [DATABASE HEADER & METADATA SUMMARY] ──────────────────────────────────{st.RESET}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}File Path:{st.RESET}         {os.path.abspath(filepath)}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}File Size:{st.RESET}         {h.file_size_bytes:,} bytes ({h.file_size_bytes / 1024:.2f} KiB)")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Magic String:{st.RESET}      {st.GREEN}{h.magic.decode('ascii', errors='replace')!r}{st.RESET} {st.DIM}(Valid SQLite 3){st.RESET}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Page Size:{st.RESET}         {st.YELLOW}{h.page_size:,} bytes{st.RESET} (Usable: {h.usable_page_size:,} bytes)")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Total Pages:{st.RESET}       {st.YELLOW}{h.effective_page_count:,}{st.RESET} (Header: {h.in_header_page_count}, Calculated: {h.computed_page_count})")
            
            # Version & Journal Mode
            journal_mode = "WAL (Write-Ahead Log)" if (h.write_version == 2 or h.read_version == 2) else "Rollback Journal / Legacy"
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Journal Mode:{st.RESET}      {st.PURPLE}{journal_mode}{st.RESET} (Write: {h.write_version}, Read: {h.read_version})")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Text Encoding:{st.RESET}     {st.CYAN}{h.encoding_str}{st.RESET}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Created By SQLite:{st.RESET} v{h.version_str} (Numeric: {h.sqlite_version_num})")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}User Version:{st.RESET}      {h.user_version}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Application ID:{st.RESET}    {h.app_id_str}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Change Counter:{st.RESET}    {h.file_change_counter}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Schema Cookie:{st.RESET}     {h.schema_cookie} (Format: {h.schema_format})")
            
            # Space Allocations
            freelist_status = f"{st.GREEN}0 pages{st.RESET}" if h.total_freelist_pages == 0 else f"{st.AMBER}{h.total_freelist_pages} pages (Trunk @ Page {h.freelist_trunk_page}){st.RESET}"
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Freelist Pages:{st.RESET}    {freelist_status}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Reserved Bytes/Pg:{st.RESET} {h.reserved_bytes} bytes")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Auto/Inc Vacuum:{st.RESET}   {'Enabled' if h.incremental_vacuum else 'Disabled'} (Largest Root: Page {h.largest_root_page})")
            print(f"{st.CYAN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

            # Schema Introspection
            schema = reader.get_schema()
            print(f"{st.BOLD}{st.PURPLE}┌── [DATABASE SCHEMA OBJECTS & ROOT PAGES] ────────────────────────────────{st.RESET}")
            if not schema:
                print(f"{st.PURPLE}│{st.RESET}  {st.DIM}(No user tables or indexes found in sqlite_schema){st.RESET}")
            else:
                print(f"{st.PURPLE}│{st.RESET}  {st.BOLD}{'TYPE':<10} {'OBJECT NAME':<26} {'ROOT PAGE':<12} {'TABLE REF':<20}{st.RESET}")
                print(f"{st.PURPLE}│{st.RESET}  {st.DARK_GRAY}{'─'*10} {'─'*26} {'─'*12} {'─'*20}{st.RESET}")
                for entry in schema:
                    type_badge = st.badge(entry.entry_type.upper(), st.BG_PURPLE if entry.entry_type == "table" else st.BG_CYAN)
                    root_str = f"Page {st.BOLD}{entry.root_page}{st.RESET}"
                    print(f"{st.PURPLE}│{st.RESET}  {type_badge:<20} {st.WHITE}{entry.name:<26}{st.RESET} {root_str:<22} {st.DIM}{entry.tbl_name}{st.RESET}")
            print(f"{st.PURPLE}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

            # Check if companion WAL file exists
            wal_path = f"{filepath}-wal"
            if os.path.exists(wal_path):
                wal_size = os.path.getsize(wal_path)
                print(f"{st.AMBER}⚡ Active Write-Ahead Log detected:{st.RESET} {wal_path} ({wal_size:,} bytes)")
                print(f"   {st.DIM}Run '{st.WHITE}python sqray.py wal {filepath}{st.RESET}{st.DIM}' to inspect active uncheckpointed frames.{st.RESET}\n")

    @staticmethod
    def tree(filepath: str, table_filter: Optional[str] = None, page_filter: Optional[int] = None, max_depth: int = 10, show_keys: bool = True):
        """Recursively traverses B-Trees and visualizes them in the terminal using box-drawing characters."""
        print(Styler.banner())
        st = Styler

        with RawSQLiteReader(filepath) as reader:
            schema = reader.get_schema()
            targets: List[Tuple[str, str, int]] = []

            if page_filter is not None:
                targets.append(("custom", f"Page {page_filter}", page_filter))
            elif table_filter:
                match = [e for e in schema if e.name.lower() == table_filter.lower() or e.tbl_name.lower() == table_filter.lower()]
                if not match:
                    print(f"{st.RED}Error:{st.RESET} No table or index matching '{table_filter}' found in schema.")
                    return
                for m in match:
                    targets.append((m.entry_type, m.name, m.root_page))
            else:
                # Add Page 1 (sqlite_schema)
                targets.append(("system", "sqlite_schema (Master Catalog)", 1))
                # Add all user tables and indexes
                for e in schema:
                    if e.root_page > 0:
                        targets.append((e.entry_type, f"{e.name} ({e.entry_type})", e.root_page))

            for obj_type, obj_name, root_pnum in targets:
                print(f"{st.BOLD}{st.CYAN}╔═══ B-Tree Hierarchy: {st.YELLOW}{obj_name}{st.RESET} {st.DIM}(Root Page {root_pnum}){st.RESET}")
                
                visited: Set[int] = set()
                SQRayCLI._render_btree_node(
                    reader=reader,
                    page_num=root_pnum,
                    prefix="",
                    is_last=True,
                    depth=0,
                    max_depth=max_depth,
                    show_keys=show_keys,
                    visited=visited
                )
                print(f"{st.CYAN}╚══════════════════════════════════════════════════════════════════════════{st.RESET}\n")

    @staticmethod
    def _render_btree_node(
        reader: RawSQLiteReader,
        page_num: int,
        prefix: str,
        is_last: bool,
        depth: int,
        max_depth: int,
        show_keys: bool,
        visited: Set[int]
    ):
        st = Styler
        branch = "└── " if is_last else "├── "
        next_prefix = prefix + ("    " if is_last else "│   ")

        if page_num in visited:
            print(f"{prefix}{branch}{st.RED}[CYCLE DETECTED: Page {page_num}]{st.RESET}")
            return
        visited.add(page_num)

        if page_num > reader.header.effective_page_count:
            print(f"{prefix}{branch}{st.RED}[Page {page_num} OUT OF BOUNDS]{st.RESET}")
            return

        try:
            page = reader.get_page(page_num)
        except Exception as ex:
            print(f"{prefix}{branch}{st.RED}[Error reading Page {page_num}: {ex}]{st.RESET}")
            return

        # Determine Badge and Color
        if page.page_type == PageType.LEAF_TABLE:
            badge = st.badge("TABLE LEAF", st.BG_GREEN)
            details = f"{st.GREEN}{page.cell_count} cells{st.RESET}"
            if page.cells and show_keys:
                rids = [c.rowid for c in page.cells if c.rowid is not None]
                if rids:
                    details += f", {st.DIM}RowIDs: [{min(rids)} .. {max(rids)}]{st.RESET}"
        elif page.page_type == PageType.INTERIOR_TABLE:
            badge = st.badge("TABLE INTERIOR", st.BG_AMBER)
            details = f"{st.AMBER}{page.cell_count} cells{st.RESET} (Pointers: {page.cell_count + 1})"
        elif page.page_type == PageType.LEAF_INDEX:
            badge = st.badge("INDEX LEAF", st.BG_CYAN)
            details = f"{st.CYAN}{page.cell_count} index keys{st.RESET}"
        elif page.page_type == PageType.INTERIOR_INDEX:
            badge = st.badge("INDEX INTERIOR", st.BG_PURPLE)
            details = f"{st.PURPLE}{page.cell_count} index keys{st.RESET} (Pointers: {page.cell_count + 1})"
        else:
            badge = st.badge(page.page_type.short_tag, st.BG_RED)
            details = f"{st.DIM}Raw/Unknown{st.RESET}"

        line = f"{prefix}{branch}{st.BOLD}{st.WHITE}Page {page_num:<4}{st.RESET} {badge} {details}"
        print(line)

        if depth >= max_depth:
            if not page.is_leaf:
                print(f"{next_prefix}└── {st.DIM}... (max depth reached){st.RESET}")
            return

        # If interior, traverse children
        if page.page_type == PageType.INTERIOR_TABLE:
            # Interior Table cells have (left_child_page, rowid)
            children = []
            for cell in page.cells:
                if cell.left_child_page:
                    children.append((cell.left_child_page, f"Key <= {cell.rowid}"))
            if page.right_child_page:
                children.append((page.right_child_page, "Right-most Child (Keys > max)"))

            for i, (ch_pnum, label) in enumerate(children):
                ch_last = (i == len(children) - 1)
                SQRayCLI._render_btree_node(
                    reader=reader,
                    page_num=ch_pnum,
                    prefix=next_prefix,
                    is_last=ch_last,
                    depth=depth + 1,
                    max_depth=max_depth,
                    show_keys=show_keys,
                    visited=visited
                )

        elif page.page_type == PageType.INTERIOR_INDEX:
            children = []
            for cell in page.cells:
                if cell.left_child_page:
                    children.append(cell.left_child_page)
            if page.right_child_page:
                children.append(page.right_child_page)

            for i, ch_pnum in enumerate(children):
                ch_last = (i == len(children) - 1)
                SQRayCLI._render_btree_node(
                    reader=reader,
                    page_num=ch_pnum,
                    prefix=next_prefix,
                    is_last=ch_last,
                    depth=depth + 1,
                    max_depth=max_depth,
                    show_keys=show_keys,
                    visited=visited
                )

    @staticmethod
    def page(filepath: str, page_num: int, raw_hex_only: bool = False):
        """Displays page header breakdown, structural regions, cell pointer table, and side-by-side hex dump."""
        print(Styler.banner())
        st = Styler

        with RawSQLiteReader(filepath) as reader:
            if page_num < 1 or page_num > reader.header.effective_page_count:
                print(f"{st.RED}Error:{st.RESET} Page number {page_num} is out of range [1 .. {reader.header.effective_page_count}]")
                return

            raw_bytes = reader.read_page_raw(page_num)
            page = reader.get_page(page_num)

            # Header Breakdown Card
            print(f"{st.BOLD}{st.CYAN}┌── [PAGE {page_num} STRUCTURAL BREAKDOWN] ────────────────────────────────────{st.RESET}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Page Number:{st.RESET}       {page_num} of {reader.header.effective_page_count}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Page Type:{st.RESET}         {page.page_type.display_name} (Flag byte: 0x{page.page_type.value:02X})")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Header Start:{st.RESET}      Byte offset {page.header_offset} {'(Offset 100 on Page 1)' if page_num == 1 else ''}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Cell Count:{st.RESET}        {st.YELLOW}{page.cell_count}{st.RESET} cells")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Cell Content Area:{st.RESET} Starts at byte {st.YELLOW}{page.cell_content_offset}{st.RESET} (0x{page.cell_content_offset:04X})")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}First Freeblock:{st.RESET}   Byte {page.first_freeblock} (0x{page.first_freeblock:04X})")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Fragmented Free:{st.RESET}   {page.fragmented_free_bytes} bytes")
            if page.right_child_page is not None:
                print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Right-most Child:{st.RESET}  Page {st.GREEN}{page.right_child_page}{st.RESET}")

            # Region Map
            hdr_size = 12 if page.right_child_page is not None else 8
            ptr_start = page.header_offset + hdr_size
            ptr_end = ptr_start + (page.cell_count * 2)
            unalloc_start = ptr_end
            unalloc_end = page.cell_content_offset

            print(f"{st.CYAN}├──────────────────────────────────────────────────────────────────────────{st.RESET}")
            print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Internal Region Offsets:{st.RESET}")
            if page_num == 1:
                print(f"{st.CYAN}│{st.RESET}   • {st.PURPLE}[0x0000 - 0x0063]{st.RESET} SQLite 100-byte Database Header")
            print(f"{st.CYAN}│{st.RESET}   • {st.CYAN}[0x{page.header_offset:04X} - 0x{ptr_start-1:04X}]{st.RESET} B-Tree Page Header ({hdr_size} bytes)")
            print(f"{st.CYAN}│{st.RESET}   • {st.GREEN}[0x{ptr_start:04X} - 0x{ptr_end-1:04X}]{st.RESET} Cell Pointer Array ({page.cell_count} pointers, {page.cell_count * 2} bytes)")
            print(f"{st.CYAN}│{st.RESET}   • {st.DARK_GRAY}[0x{unalloc_start:04X} - 0x{unalloc_end-1:04X}]{st.RESET} Unallocated Space ({max(0, unalloc_end - unalloc_start)} free bytes)")
            print(f"{st.CYAN}│{st.RESET}   • {st.AMBER}[0x{page.cell_content_offset:04X} - 0x{len(raw_bytes)-1:04X}]{st.RESET} Cell Content Area ({len(raw_bytes) - page.cell_content_offset} bytes)")
            print(f"{st.CYAN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

            # Cell Pointer Table
            if page.cells and not raw_hex_only:
                print(f"{st.BOLD}{st.WHITE}┌── [CELL POINTER ARRAY ({len(page.cells)} cells)] ──────────────────────────────────────{st.RESET}")
                print(f"{st.WHITE}│{st.RESET}  {st.BOLD}{'#':<4} {'OFFSET':<12} {'LENGTH':<10} {'KEY / ROWID':<16} {'PAYLOAD PREVIEW'}{st.RESET}")
                print(f"{st.WHITE}│{st.RESET}  {st.DARK_GRAY}{'─'*4} {'─'*12} {'─'*10} {'─'*16} {'─'*28}{st.RESET}")
                for cell in page.cells[:25]: # Limit to first 25 cells for terminal readability
                    off_str = f"0x{cell.offset:04X} ({cell.offset})"
                    len_str = f"{cell.length} B"
                    key_str = f"RowID: {cell.rowid}" if cell.rowid is not None else (f"LeftPg: {cell.left_child_page}" if cell.left_child_page else "-")
                    preview = ""
                    if cell.decoded_record:
                        preview = str(cell.decoded_record)[:40]
                    elif cell.payload:
                        preview = cell.payload[:20].hex()
                    print(f"{st.WHITE}│{st.RESET}  {cell.cell_index:<4} {off_str:<12} {len_str:<10} {key_str:<16} {st.DIM}{preview}{st.RESET}")
                if len(page.cells) > 25:
                    print(f"{st.WHITE}│{st.RESET}  {st.DIM}... and {len(page.cells) - 25} more cells{st.RESET}")
                print(f"{st.WHITE}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

            # Formatted Hex Dump with Side-by-Side ASCII
            print(f"{st.BOLD}{st.GREEN}┌── [RAW PAGE HEX DUMP (Offset 0x0000 - 0x{len(raw_bytes)-1:04X})] ─────────────────────{st.RESET}")
            print(f"{st.GREEN}│{st.RESET}  {st.DIM}OFFSET   00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F   ASCII{st.RESET}")
            print(f"{st.GREEN}│{st.RESET}  {st.DARK_GRAY}{'─'*8} {'─'*23}  {'─'*23}   {'─'*16}{st.RESET}")
            
            zero_block = b"\x00" * 16
            consecutive_zeros = 0
            folded_zeros = False

            for line_offset in range(0, len(raw_bytes), 16):
                chunk = raw_bytes[line_offset: line_offset + 16]
                
                # Check for zero folding unless raw_hex_only / --all is requested
                if not raw_hex_only and chunk == zero_block:
                    consecutive_zeros += 1
                    if consecutive_zeros > 2:
                        if not folded_zeros:
                            print(f"{st.GREEN}│{st.RESET}  {st.DARK_GRAY}*        [... repeated empty zero-fill bytes folded ... use --all to expand]{st.RESET}")
                            folded_zeros = True
                        continue
                else:
                    consecutive_zeros = 0
                    folded_zeros = False

                # Hex representation with color coding based on region
                hex_parts_1 = []
                for i in range(min(8, len(chunk))):
                    byte_val = chunk[i]
                    b_off = line_offset + i
                    colored_byte = SQRayCLI._color_byte_by_region(b_off, byte_val, page_num, page)
                    hex_parts_1.append(colored_byte)
                
                hex_parts_2 = []
                for i in range(8, len(chunk)):
                    byte_val = chunk[i]
                    b_off = line_offset + i
                    colored_byte = SQRayCLI._color_byte_by_region(b_off, byte_val, page_num, page)
                    hex_parts_2.append(colored_byte)

                hex_str_1 = " ".join(hex_parts_1).ljust(23 + (len(hex_parts_1) * (len(st.CYAN) + len(st.RESET)) if st.ENABLED else 0))
                hex_str_2 = " ".join(hex_parts_2).ljust(23 + (len(hex_parts_2) * (len(st.CYAN) + len(st.RESET)) if st.ENABLED else 0))

                # ASCII representation
                ascii_chars = []
                for b in chunk:
                    if 32 <= b <= 126:
                        ascii_chars.append(chr(b))
                    else:
                        ascii_chars.append(f"{st.DARK_GRAY}.{st.RESET}" if st.ENABLED else ".")
                ascii_str = "".join(ascii_chars)

                print(f"{st.GREEN}│{st.RESET}  {st.CYAN}{line_offset:06X}{st.RESET}  {hex_str_1}  {hex_str_2}   {ascii_str}")

            print(f"{st.GREEN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

    @staticmethod
    def _color_byte_by_region(b_off: int, byte_val: int, page_num: int, page: BTreePage) -> str:
        st = Styler
        if not st.ENABLED:
            return f"{byte_val:02X}"

        # If on page 1 and in 100-byte db header
        if page_num == 1 and b_off < 100:
            return f"{st.PURPLE}{byte_val:02X}{st.RESET}"
        
        # B-Tree Page Header
        hdr_size = 12 if page.right_child_page is not None else 8
        if page.header_offset <= b_off < page.header_offset + hdr_size:
            return f"{st.CYAN}{st.BOLD}{byte_val:02X}{st.RESET}"

        # Cell Pointers
        ptr_start = page.header_offset + hdr_size
        ptr_end = ptr_start + (page.cell_count * 2)
        if ptr_start <= b_off < ptr_end:
            return f"{st.GREEN}{byte_val:02X}{st.RESET}"

        # Cell Content Area
        if b_off >= page.cell_content_offset:
            return f"{st.AMBER}{byte_val:02X}{st.RESET}"

        # Unallocated Space
        return f"{st.DARK_GRAY}{byte_val:02X}{st.RESET}"

    @staticmethod
    def wal(filepath: str):
        """Parses and inspects Write-Ahead Log (-wal) headers and transaction frames."""
        print(Styler.banner())
        st = Styler

        wal_path = filepath if filepath.endswith("-wal") else f"{filepath}-wal"
        if not os.path.exists(wal_path):
            print(f"{st.RED}Error:{st.RESET} WAL file '{wal_path}' does not exist.")
            return

        reader = WALReader(wal_path)
        h = reader.header

        # WAL Header Summary
        print(f"{st.BOLD}{st.AMBER}┌── [WAL (WRITE-AHEAD LOG) HEADER SUMMARY] ────────────────────────────────{st.RESET}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}File Path:{st.RESET}         {os.path.abspath(wal_path)}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}File Size:{st.RESET}         {reader.file_size:,} bytes")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Magic Number:{st.RESET}      0x{h.magic:08X} ({'Big-Endian' if h.is_big_endian_checksum else 'Little-Endian'} Checksums)")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Format Version:{st.RESET}    {h.format_version}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Page Size:{st.RESET}         {h.page_size:,} bytes")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Checkpoint Seq:{st.RESET}    {h.checkpoint_seq}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Salt 1 / Salt 2:{st.RESET}   0x{h.salt1:08X} / 0x{h.salt2:08X}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Header Checksum:{st.RESET}   0x{h.checksum1:08X} : 0x{h.checksum2:08X}")
        print(f"{st.AMBER}│{st.RESET}  {st.BOLD}Total Frames:{st.RESET}      {st.YELLOW}{len(reader.frames)}{st.RESET} frames")
        print(f"{st.AMBER}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

        # Frame Table
        if not reader.frames:
            print(f"{st.DIM}No frames present in WAL log.{st.RESET}")
            return

        print(f"{st.BOLD}{st.CYAN}┌── [UN-CHECKPOINTED TRANSACTION FRAMES] ──────────────────────────────────{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}  {st.BOLD}{'FRAME':<8} {'OFFSET':<12} {'DB PAGE':<12} {'COMMIT FLAG':<22} {'CHECKSUMS'}{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}  {st.DARK_GRAY}{'─'*8} {'─'*12} {'─'*12} {'─'*22} {'─'*22}{st.RESET}")

        commit_count = 0
        dirty_pages = set()
        for f in reader.frames:
            commit_str = f"{st.GREEN}COMMIT (DB Pgs: {f.db_size_pages_after_commit}){st.RESET}" if f.is_commit else f"{st.DIM}Append{st.RESET}"
            if f.is_commit:
                commit_count += 1
            dirty_pages.add(f.page_num)

            off_str = f"0x{f.file_offset:06X}"
            pg_str = f"Page {st.BOLD}{f.page_num}{st.RESET}"
            ck_str = f"0x{f.checksum1:08X}:0x{f.checksum2:08X}"
            print(f"{st.CYAN}│{st.RESET}  {f.frame_index:<8} {off_str:<12} {pg_str:<20} {commit_str:<30} {st.DIM}{ck_str}{st.RESET}")

        print(f"{st.CYAN}├──────────────────────────────────────────────────────────────────────────{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Summary:{st.RESET} {st.YELLOW}{len(reader.frames)}{st.RESET} frames total across {st.GREEN}{commit_count}{st.RESET} commit transaction(s).")
        print(f"{st.CYAN}│{st.RESET}  {st.BOLD}Pending Modified Database Pages:{st.RESET} {sorted(list(dirty_pages))}")
        print(f"{st.CYAN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

    @staticmethod
    def map_pages(filepath: str):
        """Displays a visual 2D page allocation grid classifying each page's role."""
        print(Styler.banner())
        st = Styler

        with RawSQLiteReader(filepath) as reader:
            h = reader.header
            schema = reader.get_schema()
            total_pages = h.effective_page_count

            # Build map of root pages
            root_map: Dict[int, str] = {1: "SCHEMA"}
            for e in schema:
                root_map[e.root_page] = f"{e.entry_type.upper()}:{e.name}"

            print(f"{st.BOLD}{st.WHITE}┌── [PAGE ALLOCATION GRID MAP ({total_pages} Total Pages)] ────────────────────────{st.RESET}")
            print(f"{st.WHITE}│{st.RESET}  {st.DIM}Legend: {st.badge('P1:SCH', st.BG_PURPLE)} {st.badge('TBL-ROOT', st.BG_GREEN)} {st.badge('TBL-INT', st.BG_AMBER)} {st.badge('TBL-LEAF', st.BG_DARK)} {st.badge('IDX-ROOT', st.BG_CYAN)} {st.badge('IDX-LEAF', st.BG_BLUE)} {st.badge('FREE', st.BG_RED)}{st.RESET}\n{st.WHITE}│{st.RESET}")

            # Iterate pages
            cols = 8
            line = f"{st.WHITE}│{st.RESET}  "
            for p_num in range(1, total_pages + 1):
                try:
                    page = reader.get_page(p_num)
                    ptype = page.page_type

                    if p_num == 1:
                        cell_str = st.badge(f"P{p_num}:SCH", st.BG_PURPLE)
                    elif p_num in root_map:
                        is_tbl = "TABLE" in root_map[p_num]
                        cell_str = st.badge(f"P{p_num}:ROOT", st.BG_GREEN if is_tbl else st.BG_CYAN)
                    elif ptype == PageType.LEAF_TABLE:
                        cell_str = st.badge(f"P{p_num}:TLEAF", st.BG_DARK, st.GREEN)
                    elif ptype == PageType.INTERIOR_TABLE:
                        cell_str = st.badge(f"P{p_num}:T-INT", st.BG_AMBER)
                    elif ptype == PageType.LEAF_INDEX:
                        cell_str = st.badge(f"P{p_num}:ILEAF", st.BG_BLUE)
                    elif ptype == PageType.INTERIOR_INDEX:
                        cell_str = st.badge(f"P{p_num}:I-INT", st.BG_PURPLE)
                    else:
                        cell_str = st.badge(f"P{p_num}:FREE", st.BG_RED)
                except Exception:
                    cell_str = st.badge(f"P{p_num}:ERR", st.BG_RED)

                line += f"{cell_str} "
                if p_num % cols == 0 or p_num == total_pages:
                    print(line)
                    line = f"{st.WHITE}│{st.RESET}  "

            print(f"{st.WHITE}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

    @staticmethod
    def dump_table(filepath: str, table_name: str, limit: int = 50):
        """Driverless direct binary record extraction of table rows without SQL engine."""
        print(Styler.banner())
        st = Styler

        with RawSQLiteReader(filepath) as reader:
            schema = reader.get_schema()
            target = next((e for e in schema if e.name.lower() == table_name.lower() and e.entry_type == "table"), None)
            if not target:
                print(f"{st.RED}Error:{st.RESET} Table '{table_name}' not found in database schema.")
                return

            # Extract column names and primary key position from SQL DDL if available
            col_names = []
            pk_col_idx = None
            if target.sql:
                try:
                    ddl = target.sql
                    paren_start = ddl.find("(")
                    paren_end = ddl.rfind(")")
                    if paren_start != -1 and paren_end != -1:
                        defs = ddl[paren_start + 1: paren_end].split(",")
                        c_idx = 0
                        for d in defs:
                            tokens = d.strip().split()
                            if tokens and not tokens[0].upper() in ("PRIMARY", "FOREIGN", "CHECK", "UNIQUE", "CONSTRAINT"):
                                cname = tokens[0].replace('"', '').replace('`', '').replace("'", "")
                                col_names.append(cname)
                                d_upper = d.upper()
                                if "INTEGER" in d_upper and "PRIMARY" in d_upper and "KEY" in d_upper:
                                    pk_col_idx = c_idx
                                c_idx += 1
                except Exception:
                    pass

            print(f"{st.BOLD}{st.CYAN}┌── [PURE BINARY ROW EXTRACTION: {st.YELLOW}{target.name}{st.CYAN}] (Root Page {target.root_page}) ──────────{st.RESET}")
            
            rows: List[Tuple[int, List[Any]]] = []
            
            def collect_rows(p_num: int):
                if len(rows) >= limit:
                    return
                try:
                    page = reader.get_page(p_num)
                except Exception:
                    return

                if page.page_type == PageType.LEAF_TABLE:
                    for cell in page.cells:
                        if cell.decoded_record is not None and cell.rowid is not None:
                            rec = list(cell.decoded_record)
                            # Handle SQLite rowid alias for INTEGER PRIMARY KEY
                            if pk_col_idx is not None and pk_col_idx < len(rec) and rec[pk_col_idx] is None:
                                rec[pk_col_idx] = cell.rowid
                            elif not rec and pk_col_idx == 0:
                                rec = [cell.rowid]
                            rows.append((cell.rowid, rec))
                            if len(rows) >= limit:
                                break
                elif page.page_type == PageType.INTERIOR_TABLE:
                    for cell in page.cells:
                        if cell.left_child_page:
                            collect_rows(cell.left_child_page)
                    if page.right_child_page:
                        collect_rows(page.right_child_page)

            collect_rows(target.root_page)

            if not rows:
                print(f"{st.CYAN}│{st.RESET}  {st.DIM}(Table is empty or no valid rows decoded){st.RESET}")
            else:
                num_cols = max(len(r[1]) for r in rows)
                if not col_names or len(col_names) < num_cols:
                    col_names = [f"col_{i}" for i in range(num_cols)]

                # Compute optimal column widths
                col_widths = []
                for c_i in range(len(col_names)):
                    w = len(col_names[c_i])
                    for rid, rdata in rows:
                        if c_i < len(rdata):
                            val_str = str(rdata[c_i])
                            if len(val_str) > 40:
                                val_str = val_str[:37] + "..."
                            w = max(w, len(val_str))
                    col_widths.append(min(w, 40))

                hdr_parts = [f"{col_names[i]:<{col_widths[i]}}" for i in range(len(col_widths))]
                hdr_str = " | ".join(hdr_parts)
                print(f"{st.CYAN}│{st.RESET}  {st.BOLD}{'ROWID':<6} | {hdr_str}{st.RESET}")
                print(f"{st.CYAN}│{st.RESET}  {st.DARK_GRAY}{'─'*6}─┼─{'─'*len(hdr_str)}{st.RESET}")
                
                for rid, cols in rows:
                    val_parts = []
                    for i in range(len(col_widths)):
                        if i < len(cols):
                            val_str = str(cols[i])
                            if len(val_str) > 40:
                                val_str = val_str[:37] + "..."
                        else:
                            val_str = "NULL"
                        val_parts.append(f"{val_str:<{col_widths[i]}}")
                    row_str = " | ".join(val_parts)
                    print(f"{st.CYAN}│{st.RESET}  {st.BOLD}{st.GREEN}{rid:<6}{st.RESET} {st.DARK_GRAY}|{st.RESET} {row_str}")

                if len(rows) >= limit:
                    print(f"{st.CYAN}│{st.RESET}  {st.DIM}... limit of {limit} rows reached{st.RESET}")

            print(f"{st.CYAN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")


# ==============================================================================
# 10. INTERACTIVE REPL SHELL
# ==============================================================================

class InteractiveShell:
    """Interactive multi-command REPL shell with persistent database session."""
    
    def __init__(self, initial_file: Optional[str] = None):
        self.active_file: Optional[str] = initial_file
        if self.active_file and not os.path.exists(self.active_file):
            print(f"{Styler.RED}Warning:{Styler.RESET} Database file '{self.active_file}' does not exist.")
            self.active_file = None

    def print_repl_help(self):
        st = Styler
        print(f"\n{st.BOLD}{st.CYAN}┌── [SQRay COMMAND GUIDE] ─────────────────────────────────────────────────{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}  {st.BOLD}SESSION & FILE MANAGEMENT:{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}open <file>{st.RESET}                  Switch active database file (e.g., `open app.db`)")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}close{st.RESET}                        Unload active database")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}clear{st.RESET} | {st.WHITE}cls{st.RESET}                  Clear terminal screen")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}help{st.RESET} | {st.WHITE}?{st.RESET}                        Show this help menu")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}exit{st.RESET} | {st.WHITE}quit{st.RESET} | {st.WHITE}q{st.RESET}                 Exit SQRay")
        print(f"{st.CYAN}│{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}  {st.BOLD}INSPECTION COMMANDS (Runs on Active DB):{st.RESET}")
        print(f"{st.CYAN}│{st.RESET}    {st.CYAN}inspect{st.RESET}                      100-byte header metadata & schema catalog")
        print(f"{st.CYAN}│{st.RESET}    {st.GREEN}tree [table] [depth]{st.RESET}         Unicode B-Tree visualizer (e.g., `tree`, `tree customers 3`)")
        print(f"{st.CYAN}│{st.RESET}    {st.YELLOW}page <page_num> [--all]{st.RESET}      Structural region breakdown & hex dump (e.g., `page 2`)")
        print(f"{st.CYAN}│{st.RESET}    {st.AMBER}wal [file]{st.RESET}                   Audit Write-Ahead Log frames (e.g., `wal`)")
        print(f"{st.CYAN}│{st.RESET}    {st.PURPLE}map{st.RESET}                          2D Page allocation grid visualizer")
        print(f"{st.CYAN}│{st.RESET}    {st.WHITE}dump <table> [limit]{st.RESET}         Extract table rows from disk pages (e.g., `dump users 20`)")
        print(f"{st.CYAN}└──────────────────────────────────────────────────────────────────────────{st.RESET}\n")

    def run(self, no_clear: bool = False):
        st = Styler
        if not no_clear:
            Styler.clear_screen()
        print(Styler.banner())
        
        if self.active_file:
            print(f"{st.DIM}Active Database:{st.RESET} {st.YELLOW}{os.path.abspath(self.active_file)}{st.RESET}\n")
        else:
            print(f"{st.DIM}Type {st.WHITE}'open <file.db>'{st.RESET}{st.DIM} to load a database, {st.WHITE}'help'{st.RESET}{st.DIM} for commands, or {st.WHITE}'exit'{st.RESET}{st.DIM} to quit.{st.RESET}\n")

        while True:
            try:
                # Dynamic prompt showing active file
                if self.active_file:
                    fname = os.path.basename(self.active_file)
                    prompt_str = f"{st.CYAN}{st.BOLD}sqray{st.RESET} ({st.YELLOW}{fname}{st.RESET}) {st.AMBER}⚡ > {st.RESET}"
                else:
                    prompt_str = f"{st.CYAN}{st.BOLD}sqray{st.RESET} ({st.DIM}no db{st.RESET}) {st.AMBER}⚡ > {st.RESET}"

                raw_line = input(prompt_str).strip()
                if not raw_line:
                    continue

                parts = raw_line.split()
                cmd = parts[0].lower()
                cmd_args = parts[1:]

                # Session Commands
                if cmd in ("exit", "quit", "q", "bye"):
                    print(f"\n{st.DIM}Goodbye! ⚡{st.RESET}")
                    break

                elif cmd in ("help", "?"):
                    self.print_repl_help()

                elif cmd in ("clear", "cls"):
                    Styler.clear_screen()
                    print(Styler.banner())

                elif cmd in ("open", "use", "file", "load"):
                    if not cmd_args:
                        print(f"{st.RED}Usage:{st.RESET} open <database_path>")
                        continue
                    new_file = cmd_args[0]
                    if not os.path.exists(new_file):
                        print(f"{st.RED}Error:{st.RESET} File not found: '{new_file}'")
                    else:
                        self.active_file = new_file
                        print(f"{st.GREEN}✔ Opened database:{st.RESET} {os.path.abspath(new_file)}")

                elif cmd == "close":
                    if self.active_file:
                        print(f"{st.DIM}Closed database:{st.RESET} {self.active_file}")
                        self.active_file = None
                    else:
                        print(f"{st.DIM}No database is currently loaded.{st.RESET}")

                # Database Commands (Requires active_file)
                elif cmd == "inspect":
                    target = cmd_args[0] if cmd_args else self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    SQRayCLI.inspect(target)

                elif cmd == "tree":
                    target = self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    
                    tbl = None
                    depth = 10
                    pnum = None
                    # Flexible parsing: `tree customers 3` or `tree --table customers --depth 3`
                    if len(cmd_args) >= 1:
                        if cmd_args[0].startswith("--table"):
                            idx = cmd_args.index("--table")
                            if idx + 1 < len(cmd_args):
                                tbl = cmd_args[idx + 1]
                        elif not cmd_args[0].startswith("-"):
                            tbl = cmd_args[0]
                    
                    if len(cmd_args) >= 2 and not cmd_args[1].startswith("-"):
                        try:
                            depth = int(cmd_args[1])
                        except ValueError:
                            pass
                    elif "--depth" in cmd_args:
                        idx = cmd_args.index("--depth")
                        if idx + 1 < len(cmd_args):
                            try:
                                depth = int(cmd_args[idx + 1])
                            except ValueError:
                                pass

                    SQRayCLI.tree(target, table_filter=tbl, page_filter=pnum, max_depth=depth, show_keys=True)

                elif cmd == "page":
                    target = self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    if not cmd_args:
                        print(f"{st.RED}Usage:{st.RESET} page <page_num> [--all] [--raw]")
                        continue
                    try:
                        pnum = int(cmd_args[0])
                    except ValueError:
                        print(f"{st.RED}Error:{st.RESET} Page number must be an integer, got: {cmd_args[0]}")
                        continue
                    raw_only = "--raw" in cmd_args or "--all" in cmd_args
                    SQRayCLI.page(target, pnum, raw_hex_only=raw_only)

                elif cmd == "wal":
                    target = cmd_args[0] if cmd_args else self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    SQRayCLI.wal(target)

                elif cmd in ("map", "grid"):
                    target = cmd_args[0] if cmd_args else self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    SQRayCLI.map_pages(target)

                elif cmd == "dump":
                    target = self.active_file
                    if not target:
                        print(f"{st.RED}Error:{st.RESET} No database loaded. Use `open <file>` first.")
                        continue
                    if not cmd_args:
                        print(f"{st.RED}Usage:{st.RESET} dump <table> [limit]")
                        continue
                    tbl = cmd_args[0]
                    lim = 50
                    if len(cmd_args) >= 2:
                        try:
                            lim = int(cmd_args[1])
                        except ValueError:
                            pass
                    SQRayCLI.dump_table(target, tbl, limit=lim)

                else:
                    print(f"{st.RED}Unknown command:{st.RESET} '{cmd}'. Type {st.WHITE}'help'{st.RESET} for list of commands.")

            except (KeyboardInterrupt, EOFError):
                print(f"\n{st.DIM}Session ended. ⚡{st.RESET}")
                break
            except Exception as e:
                print(f"{st.RED}Error:{st.RESET} {e}")


# ==============================================================================
# 11. CLI ENTRYPOINT & USAGE
# ==============================================================================

def print_help():
    print(Styler.banner())
    st = Styler
    help_text = f"""
{st.BOLD}USAGE:{st.RESET}
    {st.WHITE}python sqray.py{st.RESET}                          Start Interactive REPL Shell
    {st.WHITE}python sqray.py <file>{st.RESET}                   Start Interactive REPL with file loaded
    {st.WHITE}python sqray.py <command> <file> [opt]{st.RESET}   Run single CLI command

{st.BOLD}COMMANDS:{st.RESET}
    {st.CYAN}interactive{st.RESET} [file] | {st.CYAN}repl{st.RESET} [file]
        Launch the persistent interactive shell to run multiple commands without restarting.

    {st.CYAN}inspect{st.RESET} <file>
        Parse the 100-byte SQLite header, display schema summary, root pages,
        encoding, freelist, page cache, and integrity checks.

    {st.GREEN}tree{st.RESET} <file> [--table <name>] [--page <num>] [--depth <n>] [--no-keys]
        Render the database B-Tree hierarchy in the terminal using box-drawing
        characters. Traverses interior and leaf table/index pages.

    {st.YELLOW}page{st.RESET} <file> <page_num> [--raw]
        Output a formatted side-by-side Hex & ASCII dump of a specific page,
        with color-coded structural regions (Header, Cell Pointers, Free, Content).

    {st.AMBER}wal{st.RESET} <file>
        Parse 32-byte Write-Ahead Log (-wal) header and inspect un-checkpointed
        transaction frames with commit flags and checksums.

    {st.PURPLE}map{st.RESET} <file>
        Render a 2D visual terminal grid of all pages in the file color-coded
        by page type (Root, Leaf Table, Interior Table, Index, Freelist).

    {st.WHITE}dump{st.RESET} <file> <table> [--limit <n>]
        Extract and display rows directly from disk pages using raw binary varint
        and record decoding without any database engine.

{st.BOLD}GLOBAL OPTIONS:{st.RESET}
    --no-clear          Preserve terminal scrollback instead of clearing screen

{st.BOLD}EXAMPLES:{st.RESET}
    # Open tool with database loaded:
    python sqray.py sample_btree_deep.db

    # Direct One-Shot Commands:
    python sqray.py inspect app.db
    python sqray.py tree app.db --table users
    python sqray.py page app.db 2
    python sqray.py wal app.db
    python sqray.py map app.db
    python sqray.py dump app.db users --limit 20
"""
    print(help_text)


def main():
    args = sys.argv[1:]
    
    # Check for --no-clear flag
    no_clear = False
    if "--no-clear" in args:
        no_clear = True
        args.remove("--no-clear")
    elif "--help" not in args and "-h" not in args:
        Styler.clear_screen()

    # 1. No arguments: Launch interactive REPL mode!
    if not args:
        shell = InteractiveShell()
        shell.run(no_clear=no_clear)
        sys.exit(0)

    # 2. Help flags
    if args[0] in ("-h", "--help", "help"):
        if not no_clear:
            Styler.clear_screen()
        print_help()
        sys.exit(0)

    # 3. Explicit interactive / repl command
    if args[0].lower() in ("interactive", "repl", "shell", "sh"):
        init_file = args[1] if len(args) > 1 else None
        shell = InteractiveShell(init_file)
        shell.run(no_clear=no_clear)
        sys.exit(0)

    # 4. If single argument and it's an existing file or .db/.sqlite extension, launch REPL with that file!
    KNOWN_CMDS = {"inspect", "tree", "page", "wal", "map", "dump", "interactive", "repl", "shell", "sh", "help"}
    if len(args) == 1 and args[0].lower() not in KNOWN_CMDS:
        init_file = args[0]
        shell = InteractiveShell(init_file)
        shell.run(no_clear=no_clear)
        sys.exit(0)

    cmd = args[0].lower()

    try:
        if cmd == "inspect":
            if len(args) < 2:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing file argument. Usage: sqray.py inspect <file>")
                sys.exit(1)
            SQRayCLI.inspect(args[1])

        elif cmd == "tree":
            if len(args) < 2:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing file argument. Usage: sqray.py tree <file> [options]")
                sys.exit(1)
            filepath = args[1]
            table_filter = None
            page_filter = None
            max_depth = 10
            show_keys = True

            i = 2
            while i < len(args):
                if args[i] == "--table" and i + 1 < len(args):
                    table_filter = args[i + 1]
                    i += 2
                elif args[i] == "--page" and i + 1 < len(args):
                    page_filter = int(args[i + 1])
                    i += 2
                elif args[i] == "--depth" and i + 1 < len(args):
                    max_depth = int(args[i + 1])
                    i += 2
                elif args[i] == "--no-keys":
                    show_keys = False
                    i += 1
                else:
                    i += 1
            SQRayCLI.tree(filepath, table_filter=table_filter, page_filter=page_filter, max_depth=max_depth, show_keys=show_keys)

        elif cmd == "page":
            if len(args) < 3:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing arguments. Usage: sqray.py page <file> <page_num>")
                sys.exit(1)
            filepath = args[1]
            try:
                pnum = int(args[2])
            except ValueError:
                print(f"{Styler.RED}Error:{Styler.RESET} Page number must be an integer, got: {args[2]}")
                sys.exit(1)
            raw_only = "--raw" in args or "--all" in args
            SQRayCLI.page(filepath, pnum, raw_hex_only=raw_only)

        elif cmd == "wal":
            if len(args) < 2:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing file argument. Usage: sqray.py wal <file>")
                sys.exit(1)
            SQRayCLI.wal(args[1])

        elif cmd == "map":
            if len(args) < 2:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing file argument. Usage: sqray.py map <file>")
                sys.exit(1)
            SQRayCLI.map_pages(args[1])

        elif cmd == "dump":
            if len(args) < 3:
                print(f"{Styler.RED}Error:{Styler.RESET} Missing arguments. Usage: sqray.py dump <file> <table> [--limit <n>]")
                sys.exit(1)
            filepath = args[1]
            table = args[2]
            limit = 50
            if "--limit" in args:
                idx = args.index("--limit")
                if idx + 1 < len(args):
                    limit = int(args[idx + 1])
            SQRayCLI.dump_table(filepath, table, limit=limit)

        else:
            print(f"{Styler.RED}Unknown command:{Styler.RESET} '{cmd}'\n")
            print_help()
            sys.exit(1)

    except (FileNotFoundError, ValueError) as ex:
        print(f"{Styler.RED}Error:{Styler.RESET} {ex}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Styler.DIM}Aborted by user. ⚡{Styler.RESET}")
        sys.exit(130)
    except Exception as ex:
        print(f"{Styler.RED}Unexpected Error:{Styler.RESET} {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()

