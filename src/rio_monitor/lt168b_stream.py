"""RIO main-monitor pixel packets for a proposed LT168B receiver.

Pure codec only. Not registered for any connected device. The stock EMonitor
firmware does not implement this protocol; never send these packets to it.
Pixels use the existing RIO encoder's big-endian RGB565 representation.
"""
import struct
import zlib

WIDTH = HEIGHT = 480
TILE_W, TILE_H = 32, 16
TILES = 450
FRAME_BYTES = WIDTH * HEIGHT * 2
KEY_BEGIN, DELTA_BEGIN, TILE, END, COMPRESSED_TILE, GROUP_TILE = 1, 2, 3, 4, 5, 6
HEADER = struct.Struct('<4sBBHIII')  # 20 bytes, followed by CRC32 and payload


def packet(kind, session, frame, index, payload=b''):
    if kind not in (KEY_BEGIN, DELTA_BEGIN, TILE, END, COMPRESSED_TILE, GROUP_TILE):
        raise ValueError('Unknown operation')
    if not 1 <= session <= 0xffffffff or not 1 <= frame <= 0xffffffff:
        raise ValueError('Session and frame must be nonzero uint32')
    if not 0 <= index <= TILES or len(payload) > (8194 if kind == GROUP_TILE else 1024):
        raise ValueError('Invalid tile metadata')
    head = HEADER.pack(b'RIO1', 1, kind, len(payload), session, frame, index)
    return head + struct.pack('<I', zlib.crc32(head + payload)) + payload


def tiles(pixels):
    if len(pixels) != FRAME_BYTES:
        raise ValueError('Expected complete 480x480 RGB565 frame')
    for y in range(0, HEIGHT, TILE_H):
        for x in range(0, WIDTH, TILE_W):
            yield b''.join(pixels[((y+j)*WIDTH+x)*2:((y+j)*WIDTH+x+TILE_W)*2]
                           for j in range(TILE_H))


def encode_frame(pixels, *, session, frame, acknowledged=None, compression=False, grouped=False):
    """Compare ONLY with the last fully acknowledged frame, never a sent frame.

    Caller must discard its base after any uncertain I/O and send a keyframe.
    The output is progressive; END acknowledgement establishes the new base.
    """
    current = list(tiles(pixels))
    previous = list(tiles(acknowledged)) if acknowledged is not None else None
    changed = [(i, tile) for i, tile in enumerate(current)
               if previous is None or tile != previous[i]]
    kind = KEY_BEGIN if previous is None else DELTA_BEGIN
    yield packet(kind, session, frame, len(changed))
    # Optional protocol feature; old firmware receives exactly the original wire.
    if compression:
        from lz4.block import compress
    entries = []
    for index, tile in changed:
        operation, payload, source = TILE, tile, tile
        if compression:
            packed = b'\x00' + compress(tile, store_size=False)
            if previous is not None:
                delta = (int.from_bytes(tile, 'little') ^
                         int.from_bytes(previous[index], 'little')).to_bytes(1024, 'little')
                predicted = b'\x01' + compress(delta, store_size=False)
                if len(predicted) < len(packed):
                    packed, source = predicted, delta
            if len(packed) < len(tile):
                operation, payload = COMPRESSED_TILE, packed
        entries.append((index, operation, payload, source))
    # Accepted receiver stages up to 207 decoded tiles; larger frames keep
    # compressed entries in a 208 KiB arena. Optimize only that complete-frame
    # path. Native staging keeps its original wire. Overflow frames may
    # try inexpensive grouping below, without a second HC4 compression pass.
    compact_large = (compression and len(changed) > 207 and
                     sum(len(item[2]) + 2 for item in entries) <= 208 * 1024)
    prepared = []
    for index, operation, payload, source in entries:
        if compact_large and operation == COMPRESSED_TILE:
            packed = payload[:1] + compress(source, mode='high_compression',
                                           compression=4, store_size=False)
            if len(packed) < len(payload):
                payload = packed
        prepared.append((index, operation, payload))
    if grouped and compression and len(changed) > 207:
        combined = _group_entries(current, previous, prepared,
                                  high_compression=compact_large)
        if sum(len(p) + 2 for _, _, p in combined) <= 208 * 1024:
            if not compact_large:
                # Spend HC4 only after cheap grouping proves this overflow
                # frame can be staged. Unrescuable frames keep the fast exit.
                compact = _group_entries(current, previous, prepared)
                if sum(len(p) + 2 for _, _, p in compact) <= 208 * 1024:
                    combined = compact
            prepared = combined
    for index, operation, payload in prepared:
        yield packet(operation, session, frame, index, payload)
    yield packet(END, session, frame, len(changed))


def _group_entries(current, previous, entries, *, high_compression=True):
    """Negotiate separately; combine only adjacent changed tiles in one band."""
    from lz4.block import compress
    result = []
    options = ({}, {'mode': 'high_compression', 'compression': 4}) if high_compression else ({},)
    at = 0
    while at < len(entries):
        index = entries[at][0]
        count = 1
        while (count < 8 and at + count < len(entries) and
               index % 15 + count < 15 and entries[at + count][0] == index + count):
            count += 1
        if count == 1:
            result.append(entries[at])
            at += 1
            continue
        # Rows of just these contiguous changed columns; no unchanged pixels.
        raw = b''.join(current[index + j][y * 64:(y + 1) * 64]
                       for y in range(16) for j in range(count))
        sources = [(0, raw)]
        if previous is not None:
            old = b''.join(previous[index + j][y * 64:(y + 1) * 64]
                           for y in range(16) for j in range(count))
            delta = (int.from_bytes(raw, 'little') ^
                     int.from_bytes(old, 'little')).to_bytes(len(raw), 'little')
            sources.append((1, delta))
        choices = []
        for predictor, source in sources:
            for settings in options:
                choices.append(bytes((count, predictor)) +
                               compress(source, store_size=False, **settings))
        packed = min(choices, key=len)
        old_entries = entries[at:at + count]
        if len(packed) <= 8194 and len(packed) + 24 < sum(len(p) + 24 for _, _, p in old_entries):
            result.append((index, GROUP_TILE, packed))
        else:
            result.extend(old_entries)
        at += count
    return result
