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
KEY_BEGIN, DELTA_BEGIN, TILE, END, COMPRESSED_TILE = 1, 2, 3, 4, 5
HEADER = struct.Struct('<4sBBHIII')  # 20 bytes, followed by CRC32 and payload


def packet(kind, session, frame, index, payload=b''):
    if kind not in (KEY_BEGIN, DELTA_BEGIN, TILE, END, COMPRESSED_TILE):
        raise ValueError('Unknown operation')
    if not 1 <= session <= 0xffffffff or not 1 <= frame <= 0xffffffff:
        raise ValueError('Session and frame must be nonzero uint32')
    if not 0 <= index <= TILES or len(payload) > 1024:
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


def encode_frame(pixels, *, session, frame, acknowledged=None, compression=False):
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
    for index, tile in changed:
        operation, payload = TILE, tile
        if compression:
            packed = b'\x00' + compress(tile, store_size=False)
            if previous is not None:
                delta = (int.from_bytes(tile, 'little') ^
                         int.from_bytes(previous[index], 'little')).to_bytes(1024, 'little')
                predicted = b'\x01' + compress(delta, store_size=False)
                if len(predicted) < len(packed):
                    packed = predicted
            if len(packed) < len(tile):
                operation, payload = COMPRESSED_TILE, packed
        yield packet(operation, session, frame, index, payload)
    yield packet(END, session, frame, len(changed))
