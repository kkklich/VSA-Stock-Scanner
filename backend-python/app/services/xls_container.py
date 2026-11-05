"""Validate OLE traversals before xlrd 2.0.2 reads the container.

The pinned reader recursively follows sibling/child directory pointers without
remembering visited nodes. A tiny graph can therefore expand exponentially.
Its mini-stream reader also follows chains without tracking visited sectors.
This preflight uses bounded physical sectors and visits each node/sector once.
It deliberately rejects corrupt containers rather than relying on xlrd's
best-effort recovery. Raw BIFF files have no OLE directory and pass through.
"""

import struct

from xlrd.compdoc import SIGNATURE

from app.services.portfolio import PortfolioError

MAX_CONTAINER_BYTES = 5 * 1024 * 1024
MAX_DIRECTORY_DEPTH = 128
_END = -2
_FREE = -1


def _invalid():
    raise PortfolioError("import_invalid_file", 422)


def validate_xls_container(data: bytes) -> None:
    if not data.startswith(SIGNATURE):
        return
    if not 512 <= len(data) <= MAX_CONTAINER_BYTES or data[28:30] != b"\xfe\xff":
        _invalid()
    version = struct.unpack_from("<H", data, 26)[0]
    shift, short_shift = struct.unpack_from("<HH", data, 30)
    if (version, shift) not in ((3, 9), (4, 12)) or short_shift != 6:
        _invalid()
    sector_size = 1 << shift
    # Match the pinned xlrd reader's addressing, including its 512-byte base.
    # Preflight and downstream parsing must inspect precisely the same bytes.
    sector_count, remainder = divmod(len(data) - 512, sector_size)
    if remainder or not sector_count:
        _invalid()

    def sector(sid):
        if not 0 <= sid < sector_count:
            _invalid()
        offset = 512 + sid * sector_size
        return data[offset : offset + sector_size]

    entries_per_sector = sector_size // 4
    integers = struct.Struct(f"<{entries_per_sector}i")
    fat_count = struct.unpack_from("<I", data, 44)[0]
    directory_start = struct.unpack_from("<i", data, 48)[0]
    cutoff, mini_fat_start, mini_fat_count = struct.unpack_from("<IiI", data, 56)
    extension_start, extension_count = struct.unpack_from("<iI", data, 68)
    # The header controls which allocation table xlrd selects for a stream.
    # CFB defines this cutoff as 4096; accepting an arbitrary value would make
    # a fixed-size validation rule disagree with the downstream parser.
    if cutoff != 4096:
        _invalid()
    # No FAT sector beyond this count can describe a physical file sector.
    max_fat_count = (sector_count + entries_per_sector - 1) // entries_per_sector
    if not 1 <= fat_count <= max_fat_count or extension_count > sector_count:
        _invalid()
    fat_sectors = []
    metadata_sectors = set()

    def add_fat_sector(sid):
        if sid in (_FREE, _END):
            return
        if not 0 <= sid < sector_count or sid in metadata_sectors:
            _invalid()
        if len(fat_sectors) >= fat_count:
            _invalid()
        metadata_sectors.add(sid)
        fat_sectors.append(sid)

    for sid in struct.unpack_from("<109i", data, 76):
        add_fat_sector(sid)

    extension_seen = set()
    sid = extension_start
    # xlrd tolerates 0/-1 when no extension sectors are declared.
    if extension_count == 0 and sid in (0, _FREE, _END):
        sid = _END
    while sid not in (_FREE, _END, -4):
        if sid in metadata_sectors or len(extension_seen) >= extension_count:
            _invalid()
        values = integers.unpack(sector(sid))
        metadata_sectors.add(sid)
        extension_seen.add(sid)
        for fat_sid in values[:-1]:
            add_fat_sector(fat_sid)
        sid = values[-1]
    if len(extension_seen) != extension_count or len(fat_sectors) != fat_count:
        _invalid()

    fat = []
    for sid in fat_sectors:
        fat.extend(integers.unpack(sector(sid)))
    directory = []
    sid = directory_start
    while sid != _END:
        if sid in metadata_sectors or not 0 <= sid < sector_count or sid >= len(fat):
            _invalid()
        metadata_sectors.add(sid)
        contents = sector(sid)
        for offset in range(0, sector_size, 128):
            entry_type = contents[offset + 66]
            links = struct.unpack_from("<iii", contents, offset + 68)
            first, size = struct.unpack_from("<iQ", contents, offset + 116)
            directory.append((entry_type, *links, first, size))
        sid = fat[sid]
    if not directory or directory[0][0] != 5:
        _invalid()

    seen = {0}
    pending = [(directory[0][3], 1)]
    while pending:
        node, depth = pending.pop()
        if node == _FREE:
            continue
        if (
            not 0 <= node < len(directory)
            or node in seen
            or depth > MAX_DIRECTORY_DEPTH
        ):
            _invalid()
        seen.add(node)
        entry_type, left, right, child, _, size = directory[node]
        if entry_type not in (1, 2):
            _invalid()
        if size > len(data) - 512:
            _invalid()
        pending.extend(((left, depth + 1), (right, depth + 1)))
        if entry_type == 1:
            pending.append((child, depth + 1))

    def claim_chain(first, table, limit, occupied, expected):
        """Claim every sector once, requiring the declared stream length."""
        if expected == 0 and first in (_FREE, _END):
            return []
        chain = []
        current = first
        while current != _END:
            if (
                not 0 <= current < limit
                or current >= len(table)
                or current in occupied
                or len(chain) >= expected
            ):
                _invalid()
            occupied.add(current)
            chain.append(current)
            current = table[current]
        if len(chain) != expected:
            _invalid()
        return chain

    _, _, _, _, root_start, root_size = directory[0]
    if root_size > len(data) - 512 or root_size % 64:
        _invalid()
    # xlrd tolerates either negative sentinel for an empty root mini-stream.
    if root_size or root_start >= 0:
        claim_chain(root_start, fat, sector_count, metadata_sectors,
                    (root_size + sector_size - 1) // sector_size)
    mini_count = root_size // 64
    if mini_fat_count > (mini_count + entries_per_sector - 1) // entries_per_sector:
        _invalid()
    mini_fat_sectors = claim_chain(
        mini_fat_start, fat, sector_count, metadata_sectors, mini_fat_count
    )
    mini_fat = []
    for sid in mini_fat_sectors:
        mini_fat.extend(integers.unpack(sector(sid)))

    mini_owned = set()
    for node in seen - {0}:
        entry_type, _, _, _, first, size = directory[node]
        if entry_type != 2:
            continue
        if size < cutoff:
            claim_chain(first, mini_fat, mini_count, mini_owned, (size + 63) // 64)
        else:
            claim_chain(first, fat, sector_count, metadata_sectors,
                        (size + sector_size - 1) // sector_size)
