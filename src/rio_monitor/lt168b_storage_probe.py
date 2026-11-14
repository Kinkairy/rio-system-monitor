"""Explicit read-only diagnostic; never called by automatic connection.

Physical SFDP density is not available media space. Actual JEDEC and resource
header must still be checked against board evidence before implementing writes.
"""
import hashlib
import struct
import zlib
from .lt168b_display import validate_hello


def decode_reply(data, op, offset):
    if op not in (0, 1, 2) or not 0 <= offset < 4096 or (op == 0 and offset):
        raise ValueError('Invalid probe range')
    n = 8 if op == 0 else min(44, 4096 - offset)
    if len(data) != 64 or data[:6] != b'RISP\x01' + bytes([op]):
        raise ValueError('Invalid storage probe reply')
    if zlib.crc32(data[:60]) != int.from_bytes(data[60:], 'little'):
        raise ValueError('Corrupt storage probe reply')
    status, at, length = struct.unpack_from('<HHH', data, 6)
    if (at, length) != (offset, n) or data[12:16] != b'\x01\0\0\0' or any(data[16+n:60]):
        raise ValueError('Mismatched storage probe reply')
    if status:
        raise OSError('Storage probe stopped with status %d' % status)
    return data[16:16+n]


def sfdp_density(data):
    # JESD216 basic-parameter DWORD2; field interpretation also documented in
    # Linux drivers/mtd/spi-nor/sfdp.c. This is an independent bounded parser.
    if len(data) < 16 or data[:4] != b'SFDP' or data[5] != 1:
        return None
    count = data[6] + 1
    if 8 + count * 8 > len(data):
        return None
    tables = []
    for at in range(8, 8 + count * 8, 8):
        h = data[at:at+8]
        ptr = int.from_bytes(h[4:7], 'little')
        if h[0] == 0 and h[7] == 0xff and h[2] == 1 and h[3] >= 9:
            if ptr < 8 + count*8 or ptr + h[3]*4 > len(data):
                return None
            tables.append((h[1], ptr))
    if not tables:
        return None
    ptr = max(tables)[1]
    density = int.from_bytes(data[ptr+4:ptr+8], 'little')
    if density & 0x80000000:
        exponent = density & 0x7fffffff
        if not 3 <= exponent <= 35:
            return None
        bits = 1 << exponent
    else:
        bits = density + 1
    if bits % 8 or bits < 32768:
        return None
    return bits // 8


def collect(transport, record=lambda event: None):
    validate_hello(transport.control(0xc1, 0x52, 0, 0, 32))
    def read(op, offset):
        raw = transport.control(0xc1, 0x54, op, offset, 64)
        record(dict(op=op, offset=offset, response=raw.hex()))
        return decode_reply(raw, op, offset)
    jedec = read(0, 0)
    # No retries, no mode or protocol reset, no media/firmware writes.
    result = dict(jedec_raw=jedec.hex(), sfdp_density_bytes=None,
                  available_media_bytes=None, storage_write_supported=False)
    # Do not interpret NAND/dummy-prefixed/empty identity as a NOR command set.
    if jedec[0] in (0, 0xff, 0x7f) or jedec[1] in (0, 0xff, 0xaa, 0xab) or not 0x10 <= jedec[2] <= 0x1b:
        result['identification'] = 'unqualified_identity_no_further_reads'
        return result
    sfdp = b''.join(read(1, at) for at in range(0, 4096, 44))
    density = sfdp_density(sfdp)
    if density is None:
        result.update(identification='unqualified_sfdp_no_resource_read', sfdp_hex=sfdp.hex())
        return result
    header = b''.join(read(2, at) for at in range(0, 4096, 44))
    return dict(jedec_raw=jedec.hex(), sfdp_density_bytes=density,
                available_media_bytes=None, resource_header_sha256=hashlib.sha256(header).hexdigest(),
                sfdp_hex=sfdp.hex(), resource_header_hex=header.hex(),
                storage_write_supported=False)


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    from .settings import acquire_instance
    from .display_protocols import enumerate_paths, device_id
    from .winusb import WinUSB
    parser = argparse.ArgumentParser(description='Read LT168B resource flash identity only. Close RIO first; requires separately approved probe firmware.')
    parser.add_argument('--journal', type=Path, required=True)
    args = parser.parse_args(argv)
    # Refuse overwriting evidence, including failed attempts.
    with args.journal.open('x', encoding='utf-8') as output:
        output.write('{}\n')
    journal = dict(events=[], error=None)
    transport = None
    def record(event):
        journal['events'].append(event)
        args.journal.write_text(json.dumps(journal, indent=2)+'\n', encoding='utf-8')
    try:
        instance = acquire_instance()
        if instance is None:
            raise RuntimeError('Close RIO before probing storage')
        paths = enumerate_paths()
        if len(paths) != 1 or device_id(paths[0]) != (0xffff, 0x168b):
            raise RuntimeError('Connect exactly one qualified RIO LT168B screen')
        transport = WinUSB(paths[0], profile='lt168b-bench')
        journal['result'] = collect(transport, record)
    except Exception as exc:
        journal['error'] = str(exc)
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception as exc:
                journal['close_error'] = str(exc)
        args.journal.write_text(json.dumps(journal, indent=2)+'\n', encoding='utf-8')
    return 1 if journal.get('error') or journal.get('close_error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
