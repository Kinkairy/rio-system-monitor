"""Read the current NetEase song and playback clock on supported Windows builds."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct

from .coreaudio import _installed_client, _PATH
from .platforms import Candidate, normalized, same_artists


# NetEase 3.1.43.205627 x64. Validate the on-disk DLL and the actual loaded
# instruction that writes the playback clock before reading its single double.
_DLL_SHA256 = '48f4b79fc0eb7fbcb955835463a71cd866c81055b0a546990e8ab644e886b920'
_IMAGE_SIZE = 0x2728000
_CLOCK_STORE_RVA = 0xBE557
_CLOCK_STORE = bytes.fromhex('f20f113d799f0e02')
_CLOCK_RVA = 0x21A84D8


class _ModuleEntry(c.Structure):
    _fields_ = [
        ('size', w.DWORD), ('module_id', w.DWORD), ('pid', w.DWORD),
        ('global_usage', w.DWORD), ('process_usage', w.DWORD),
        ('base', c.c_void_p), ('image_size', w.DWORD), ('module', w.HMODULE),
        ('name', w.WCHAR * 256), ('path', w.WCHAR * 260),
    ]


def _player_module(kernel, pid, dll):
    snapshot = kernel.CreateToolhelp32Snapshot
    snapshot.argtypes = (w.DWORD, w.DWORD)
    snapshot.restype = w.HANDLE
    first, following = kernel.Module32FirstW, kernel.Module32NextW
    first.argtypes = following.argtypes = (w.HANDLE, c.POINTER(_ModuleEntry))
    first.restype = following.restype = w.BOOL
    handle = snapshot(0x00000008, pid)  # Modules of the same process architecture.
    if not handle or handle == c.c_void_p(-1).value:
        return None
    try:
        entry = _ModuleEntry(size=c.sizeof(_ModuleEntry))
        available = first(handle, c.byref(entry))
        while available:
            if entry.path.casefold() == str(dll).casefold():
                return entry.base if entry.image_size == _IMAGE_SIZE else None
            available = following(handle, c.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return None


def _read(kernel, handle, address, size):
    buffer = c.create_string_buffer(size)
    copied = c.c_size_t()
    if kernel.ReadProcessMemory(handle, address, buffer, size, c.byref(copied)) and copied.value == size:
        return buffer.raw
    return None


class PlaybackClock:
    def __init__(self):
        self.pid = None
        self.kernel = None
        self.handle = None
        self.address = None

    def _open(self, pid):
        if not _installed_client(pid):
            return
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
        kernel.OpenProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = (w.HANDLE,)
        kernel.CloseHandle.restype = w.BOOL
        kernel.ReadProcessMemory.argtypes = (w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t))
        kernel.ReadProcessMemory.restype = w.BOOL
        dll = Path(_PATH).with_name('cloudmusic.dll')
        base = _player_module(kernel, pid, dll)
        if not base:
            return
        try:
            with dll.open('rb') as file:
                if hashlib.file_digest(file, 'sha256').hexdigest() != _DLL_SHA256:
                    return
        except OSError:
            return
        handle = kernel.OpenProcess(0x0010, False, pid)  # PROCESS_VM_READ only.
        if not handle:
            return
        if _read(kernel, handle, base + _CLOCK_STORE_RVA, len(_CLOCK_STORE)) != _CLOCK_STORE:
            kernel.CloseHandle(handle)
            return
        self.kernel, self.handle, self.address = kernel, handle, base + _CLOCK_RVA

    def read(self, pid):
        if pid != self.pid:
            self.close()
            self.pid = pid
            self._open(pid)
        if self.handle:
            sample = _read(self.kernel, self.handle, self.address, 8)
            if sample is not None:
                return struct.unpack('<d', sample)[0]
        return None

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
        self.pid = self.kernel = self.handle = self.address = None


class PlaybackQueue:
    """Match the visible song with an exact ID in the player's current queue."""
    def __init__(self):
        self.key = None
        self.record = None

    def find(self, title, artist):
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            return None
        queue = Path(local) / 'NetEase' / 'CloudMusic' / 'webdata' / 'file' / 'playingList'
        limit = 16 * 1024 * 1024
        try:
            info = queue.stat()
            if info.st_size > limit:
                return None
            key = (queue, info.st_mtime_ns, info.st_size, title, artist)
            if key == self.key:
                return self.record
            with queue.open('rb') as file:
                data = file.read(limit + 1)
            if len(data) > limit:
                return None
            body = json.loads(data)
            items = body.get('list') if isinstance(body, dict) else None
            if not isinstance(items, list):
                return None
        except (OSError, ValueError):
            return None

        matches = set()
        for entry in items:
            item = entry.get('track') if isinstance(entry, dict) else None
            if not isinstance(item, dict) or normalized(item.get('name', '')) != normalized(title):
                continue
            names = item.get('artists')
            if not isinstance(names, list):
                continue
            artists = tuple(a.get('name') if isinstance(a, dict) else None for a in names)
            milliseconds = item.get('duration')
            ident = str(item.get('id', ''))
            if (not artists or any(not isinstance(name, str) or not name for name in artists)
                or not same_artists(artist, artists) or not re.fullmatch(r'[1-9][0-9]{0,19}', ident)
                or type(milliseconds) not in (int, float) or not 0 < milliseconds <= 86_400_000):
                continue
            album = item.get('album')
            name = album.get('name') if isinstance(album, dict) else None
            matches.add(Candidate(ident, title, artists, name if isinstance(name, str) else '', milliseconds / 1000))
        self.key = key
        self.record = matches.pop() if len(matches) == 1 else None
        return self.record
