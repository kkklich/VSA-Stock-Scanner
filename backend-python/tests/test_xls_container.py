"""Reject recursive OLE directory amplification before xlrd traverses it."""

import struct
from pathlib import Path

import pytest
from xlrd import compdoc

from app.services.portfolio import PortfolioError
from app.services.xls_container import MAX_DIRECTORY_DEPTH, validate_xls_container
from app.services.xtb_import import read_tables


def _entry(name, *, kind=2, left=-1, right=-1, child=-1, first=-2, size=0):
    result = bytearray(128)
    encoded = (name + "\0").encode("utf-16-le")
    result[: len(encoded)] = encoded
    struct.pack_into("<HBBiii", result, 64, len(encoded), kind, 1, left, right, child)
    struct.pack_into("<iQ", result, 116, first, size)
    return bytes(result)


def _container(entries, *, extension=False, sector_size=512):
    """A complete OLE directory, with no workbook or mini-stream needed."""
    header = bytearray(512)
    header[:8] = compdoc.SIGNATURE
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3 if sector_size == 512 else 4,
                     0xFFFE, 9 if sector_size == 512 else 12, 6)
    start = 2 if extension else 1
    struct.pack_into("<II", header, 44, 1, start)
    struct.pack_into("<IiIiI", header, 56, 4096, -2, 0, 1 if extension else -2,
                     1 if extension else 0)
    struct.pack_into("<109i", header, 76, *([-1] * 109))
    if not extension:
        struct.pack_into("<i", header, 76, 0)

    directories = b"".join(entries)
    directories += bytes(-len(directories) % sector_size)
    count = len(directories) // sector_size
    fat = [-1] * (sector_size // 4)
    fat[0] = -3
    if extension:
        fat[1] = -4
    for sid in range(start, start + count):
        fat[sid] = sid + 1 if sid < start + count - 1 else -2
    result = bytes(header) + struct.pack(f"<{len(fat)}i", *fat)
    if extension:
        difat = [0] + [-1] * (sector_size // 4 - 2) + [-2]
        result += struct.pack(f"<{len(difat)}i", *difat)
    return result + directories


def _dag(levels):
    return [_entry("Root Entry", kind=5, child=1)] + [
        _entry(f"Node {index}", left=index + 1, right=index + 1)
        if index < levels else _entry(f"Node {index}")
        for index in range(1, levels + 1)
    ]


def test_safe_small_graph_demonstrates_upstream_amplification():
    data = _container(_dag(6))
    # Keep the demonstration small: six physical nodes cause 63 visits.
    assert len(compdoc.CompDoc(data).dirlist[0].children) == 63
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(data)


def test_large_directory_dag_is_rejected_before_upstream_traversal(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted directory graph reached xlrd's recursive traversal")

    monkeypatch.setattr(compdoc, "_build_family_tree", forbidden)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(_container(_dag(30)), "history.xls")


@pytest.mark.parametrize("extension", [False, True])
@pytest.mark.parametrize("sector_size", [512, 4096])
def test_distinct_directory_nodes_and_storage_children_are_supported(extension, sector_size):
    entries = [
        _entry("Root Entry", kind=5, child=2),
        _entry("First"),
        _entry("Folder", kind=1, left=1, right=3, child=4),
        _entry("Last"),
        _entry("Nested"),
    ]
    data = _container(entries, extension=extension, sector_size=sector_size)
    validate_xls_container(data)
    assert compdoc.CompDoc(data).dirlist[0].children == [1, 2, 3]


def test_real_xtb_container_and_raw_biff_remain_supported():
    data = (Path(__file__).parent / "fixtures/xtb_cash_history.xls").read_bytes()
    validate_xls_container(data)
    validate_xls_container(b"\x09\x08\x08\0\0\x06\x05\0\0\0\0\0")


@pytest.mark.parametrize("links", [
    {"left": 1},  # Self cycle.
    {"right": 0},  # Re-enter the root.
    {"left": 2, "right": 2},  # Same node through both sibling links.
    {"left": 999},  # Outside the directory stream.
    {"left": -2},  # Not the directory's -1 null pointer.
    {"kind": 1, "right": 2, "child": 2},  # Two parents own one node.
])
def test_invalid_or_shared_directory_links_are_rejected(links):
    entries = [_entry("Root Entry", kind=5, child=1), _entry("Child", **links),
               _entry("Leaf")]
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(_container(entries))


@pytest.mark.parametrize("depth,accepted", [(MAX_DIRECTORY_DEPTH, True),
                                           (MAX_DIRECTORY_DEPTH + 1, False)])
def test_directory_depth_is_bounded_before_recursive_xlrd_calls(depth, accepted):
    entries = [_entry("Root Entry", kind=5, child=1)] + [
        _entry(str(index), left=index + 1 if index < depth else -1)
        for index in range(1, depth + 1)
    ]
    data = _container(entries)
    if accepted:
        validate_xls_container(data)
    else:
        with pytest.raises(PortfolioError, match="import_invalid_file"):
            validate_xls_container(data)


@pytest.mark.parametrize("offset,format,value", [
    (30, "H", 20),  # Unsupported sector size.
    (44, "I", 0xFFFFFFFF),  # Unbounded declared FAT count.
    (48, "i", 999),  # Directory starts outside physical sectors.
    (76, "i", 999),  # FAT sector outside the file.
    (80, "i", 0),  # FAT sector listed twice.
    (512 + 4, "i", 1),  # Directory FAT chain loops.
    (512 + 4, "i", -1),  # Directory chain lacks end-of-chain marker.
])
def test_invalid_sector_metadata_is_rejected(offset, format, value):
    data = bytearray(_container([_entry("Root Entry", kind=5)]))
    struct.pack_into("<" + format, data, offset, value)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(bytes(data))


def test_difat_cycle_is_rejected():
    data = bytearray(_container([_entry("Root Entry", kind=5)], extension=True))
    struct.pack_into("<i", data, 512 + 512 + 508, 1)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(bytes(data))


@pytest.mark.parametrize("cut", [8, 100, 511, 1023])
def test_truncated_containers_are_rejected(cut):
    data = _container([_entry("Root Entry", kind=5)])[:cut]
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(data)


def _mini_container(payload, *, name="Workbook", duplicate=False):
    mini_count = (len(payload) + 63) // 64
    entries = [
        _entry("Root Entry", kind=5, child=1, first=2, size=mini_count * 64),
        _entry(name, first=0, size=len(payload), right=2 if duplicate else -1),
    ]
    if duplicate:
        entries.append(_entry("Other", first=0, size=len(payload)))
    result = bytearray(_container(entries))
    struct.pack_into("<iI", result, 60, 3, 1)
    struct.pack_into("<ii", result, 512 + 8, -2, -2)
    result.extend(payload + bytes(512 - len(payload)))
    mini_fat = [-1] * 128
    for index in range(mini_count):
        mini_fat[index] = index + 1 if index < mini_count - 1 else -2
    result.extend(struct.pack("<128i", *mini_fat))
    return bytes(result)


@pytest.mark.parametrize("name", ["Workbook", "Book"])
@pytest.mark.parametrize("length", [1, 64, 100])
def test_valid_mini_stream_chains_preserve_workbook_extraction(name, length):
    payload = bytes(range(length))
    data = _mini_container(payload, name=name)
    validate_xls_container(data)
    extracted, start, size = compdoc.CompDoc(data).locate_named_stream(name)
    assert extracted[start : start + size] == payload


@pytest.mark.parametrize("name", ["Workbook", "Book"])
def test_mini_stream_cycle_is_rejected_before_any_xlrd_stream_read(monkeypatch, name):
    data = bytearray(_mini_container(b"x" * 64, name=name))
    struct.pack_into("<i", data, 2048, 0)

    def forbidden(*args, **kwargs):
        pytest.fail("Unvalidated mini-stream chain reached xlrd")

    monkeypatch.setattr(compdoc.CompDoc, "_get_stream", forbidden)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        read_tables(bytes(data), "history.xls")


@pytest.mark.parametrize("offset,format,value", [
    (56, "I", 0),  # Header selects a different allocation table.
    (56, "I", 0xFFFFFFFF),  # Negative cutoff in the downstream signed reader.
    (60, "i", 2),  # Mini-FAT overlaps the root mini-stream's sector.
    (64, "I", 0xFFFFFFFF),  # Declared mini-FAT count exceeds physical capacity.
    (1024 + 116, "i", -1),  # Nonempty root stream has no physical chain.
    (1024 + 120, "Q", 0xFFFFFFFF),  # Negative root size downstream.
    (1024 + 120, "Q", 0),  # Mini stream IDs point into an empty root stream.
    (1024 + 128 + 120, "Q", 0xFFFFFFFF),  # Negative Workbook size downstream.
    (1024 + 128 + 116, "i", 8),  # First mini sector outside the root stream.
    (2048, "i", -2),  # Chain too short for a two-sector Workbook.
    (2048, "i", 8),  # Next mini sector outside the root stream.
    (2048, "i", -1),  # Mini chain ends with a free-sector marker.
    (2052, "i", 0),  # Two-node cycle.
])
def test_invalid_mini_stream_metadata_is_rejected(offset, format, value):
    data = bytearray(_mini_container(b"x" * 100))
    struct.pack_into("<" + format, data, offset, value)
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(bytes(data))


def test_different_streams_cannot_share_mini_sectors():
    with pytest.raises(PortfolioError, match="import_invalid_file"):
        validate_xls_container(_mini_container(b"x" * 100, duplicate=True))


def test_empty_root_and_mini_fat_accept_the_legacy_free_sentinel():
    data = bytearray(_container([_entry("Root Entry", kind=5, first=-1)]))
    struct.pack_into("<i", data, 60, -1)
    validate_xls_container(bytes(data))
    assert compdoc.CompDoc(data).SSCS == ""
