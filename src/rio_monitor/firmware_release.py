"""Inputs for the eM133-V3 release verified on a 480 by 480 LT168B panel."""
import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import firmware_segments as seg

FILENAME = 'em133-v3-rio-startup.zip'
PLAYER_SHA = '1a7eb3b36bd3f93f137671a1381d34860860b0afe6577074c86c2e5344eed727'
BANK_SHA = 'c2d44bd7aa143a865bc3b5aaa2f745f67feb01a60d1b43a8729082f9745bd965'
HELPER_SHA = '36ef7249664bf671d179762858f1a8cf66e555432176054ae03a160930266cec'
PREVIOUS_SHA = 'ee14534fc7606a56db7f0b5cb07e305b8cc2d8303d39a55fb4d459b6d3cb87f8'
LEGACY_SHA = '30780997a3baf2d0002462443c3922f4d54997f1b6e7929c8e80b15a15883a9a'
FACTORY_SHA = '0ee16305f4965822abb4143e7f90a031467445cf9aa6fe5606d3cc3b3da513f2'
CHAIN_ROOT = bytes.fromhex('4689499a4ff4c9fc59c42b752983f9a24647aedded587b2a9db310248f6d0f68')
MEMBERS = {
    'player.bin': (seg.LOW_END, PLAYER_SHA),
    'animation.bin': (seg.BANK_END - seg.BANK, BANK_SHA),
    'maintenance.bin': (seg.LOW_END, HELPER_SHA),
    'previous-rio.bin': (seg.LOW_END, PREVIOUS_SHA),
    'legacy-rio.bin': (seg.LOW_END, LEGACY_SHA),
}

@dataclass(frozen=True)
class Release:
    player: seg.Image
    bank: bytes
    helper: seg.Image
    previous: tuple

    def describe(self):
        return dict(board=seg.BOARD, animation_frames=216, animation_period_ms=7200,
                    player_sha256=PLAYER_SHA, animation_sha256=BANK_SHA,
                    maintenance_sha256=HELPER_SHA, protected_bytes=seg.BANK-seg.LOW_END)

def read_release(path):
    if Path(path).stat().st_size>2*1024*1024:
        raise ValueError('Unexpected RIO startup firmware size')
    try:
        return _read_images(path)
    except zipfile.BadZipFile as exc:
        raise ValueError('Invalid RIO startup firmware archive') from exc

def _read_images(path):
    with zipfile.ZipFile(path) as archive:
        if sorted(archive.namelist()) != sorted(MEMBERS):
            raise ValueError('Unexpected files in RIO startup firmware')
        parts = {}
        for name, (length, digest) in MEMBERS.items():
            if archive.getinfo(name).file_size != length:
                raise ValueError('Unexpected firmware length: '+name)
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Firmware checksum mismatch: '+name)
            parts[name] = data
    return Release(seg.Image(0, parts['player.bin']), parts['animation.bin'],
                   seg.Image(0, parts['maintenance.bin']), (parts['previous-rio.bin'], parts['legacy-rio.bin']))

def bundled(folder):
    return read_release(Path(folder)/FILENAME)

def selected(path, folder):
    if Path(path).stat().st_size<=2*1024*1024:
        return read_release(path)
    original=seg.load_package(path)
    if (Path(folder)/FILENAME).is_file():
        return bundled(folder)
    return original

def sector_records(bank):
    count = (seg.BANK_END-seg.BANK)//seg.SECTOR
    if len(bank)!=count*seg.SECTOR or hashlib.sha256(bank).hexdigest()!=BANK_SHA:
        raise ValueError('Unexpected animation image')
    records = [None]*count
    next_digest = bytes(32)
    for i in reversed(range(count)):
        frame = bank[i*seg.SECTOR:(i+1)*seg.SECTOR] + next_digest
        records[i] = frame
        next_digest = hashlib.sha256(frame).digest()
    if next_digest != CHAIN_ROOT:
        raise ValueError('Animation and maintenance releases differ')
    return records
