"""NetEase desktop fallback when its Windows media session is unavailable."""
import ctypes as c
from dataclasses import replace
import math
import sys
import time

from .netease_timing import PlaybackClock, PlaybackQueue
from .platforms import identify_player, normalized
from .state import Track

SOURCE = 'netease-window-audio'


def parse_title(value):
    if not value or len(value) > 512 or any(ord(x) < 32 for x in value):
        return None
    # Ambiguous separators are deliberately not guessed.
    parts = value.split(' - ')
    if len(parts) != 2 or any(not p.strip() for p in parts):
        return None
    title, artist = (p.strip() for p in parts)
    if title in ('网易云音乐', 'CloudMusic') or artist in ('网易云音乐', 'CloudMusic'):
        return None
    return title, artist


def _windows(pids):
    if sys.platform != 'win32' or not pids:
        return []
    from ctypes import wintypes as w
    user = c.WinDLL('user32', use_last_error=True)
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = (callback_type, w.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (w.HWND, c.POINTER(w.DWORD))
    user.GetWindowTextLengthW.argtypes = (w.HWND,)
    user.GetWindowTextW.argtypes = (w.HWND, w.LPWSTR, c.c_int)
    user.IsWindowVisible.argtypes = (w.HWND,)
    user.GetClassNameW.argtypes = (w.HWND, w.LPWSTR, c.c_int)
    result = []
    @callback_type
    def visit(hwnd, _):
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value not in pids:
            return True
        if not user.IsWindowVisible(hwnd):
            window_class = c.create_unicode_buffer(64)
            user.GetClassNameW(hwnd, window_class, len(window_class))
            if window_class.value != 'OrpheusBrowserHost':
                return True
        length = user.GetWindowTextLengthW(hwnd)
        if 0 < length <= 512:
            value = c.create_unicode_buffer(length + 1)
            user.GetWindowTextW(hwnd, value, length + 1)
            result.append((pid.value, value.value))
        return True
    if not user.EnumWindows(visit, 0):
        return []
    return result


def metadata_track(titles, audible, now):
    if not audible:
        return None
    matches = {x for value in titles if (x := parse_title(value))}
    if len(matches) != 1:
        return None
    title, artist = matches.pop()
    # playing stays false: audio activity is not a transport-state assertion.
    return Track(source=SOURCE, title=title, artist=artist, observed=now)


def has_native_netease(items):
    return any(app != SOURCE and identify_player(app) == 'netease' for app, _, _ in items)


def append_fallback(items, track):
    if track is None or has_native_netease(items):
        return items
    return [*items, (SOURCE, track.position is None or track.playing, track)]


def choose_session(items, preference, previous):
    from .state import select_session
    # A remembered metadata-only source must not outrank real playback.
    if previous == SOURCE and any(app != SOURCE and playing for app, playing, _ in items):
        previous = ''
    return select_session(items, preference, previous)


class NetEasePlayback:
    def __init__(self):
        self.clock = PlaybackClock()
        self.queue = PlaybackQueue()
        self.identity = None
        self.record = None
        self.record_due = 0
        self.previous = None

    def close(self):
        self.clock.close()
        self.identity = self.record = self.previous = None
        self.record_due = 0

    def fill_native_timeline(self, track):
        if track.duration > 0 and track.position is not None:
            self.close()
            return track

        record = self.queue.find(track.title, track.artist) if track.title and track.artist else None
        if (record is None or (track.album and normalized(track.album) != normalized(record.album))
                or (track.duration > 0 and abs(track.duration - record.duration) > 3)):
            self.close()
            return replace(track, position=None)

        if track.position is not None and track.position <= record.duration + .5:
            self.close()
            return replace(track, duration=record.duration, position=min(track.position, record.duration))

        try:
            sampled = self.observe()
        except Exception:
            self.close()
            sampled = None
        if sampled is not None and sampled.recording_id == record.ident and sampled.position is not None:
            return replace(track, duration=record.duration, position=sampled.position,
                           observed=sampled.observed, sampled_position=True)
        return replace(track, position=None)

    def observe(self, timing=True):
        from .coreaudio import active_cloudmusic_pids
        audible = active_cloudmusic_pids()
        pids = set(audible)
        if timing and self.identity and self.previous:
            # Keep the verified current song across a pause or a quiet passage.
            pids.add(self.identity[0])
        now = time.monotonic()
        windows = _windows(pids)
        legacy = metadata_track([title for pid, title in windows if pid in audible], bool(audible), now)
        matches = {(pid, *song) for pid, caption in windows if (song := parse_title(caption))}
        if not timing or len(matches) != 1:
            self.close()
            return legacy

        identity = matches.pop()
        pid, title, artist = identity
        if identity != self.identity:
            self.identity = identity
            self.record = self.previous = None
            self.record_due = 0
        if now >= self.record_due:
            self.record_due = now + 1
            self.record = self.queue.find(title, artist)
        record = self.record
        if legacy is not None and record is not None:
            legacy = replace(legacy, cover_url=record.cover_url)
        position = self.clock.read(pid)
        if (position is None or not math.isfinite(position) or record is None
                or not 0 <= position <= record.duration + .5):
            self.previous = None
            return legacy

        playing = False
        if self.previous and self.previous[0] == record.ident:
            _, before, when = self.previous
            # A seek changes the displayed position immediately. A jump is not
            # evidence that a paused player resumed.
            elapsed = now - when
            playing = 0 < elapsed <= 3 and .015 < position - before <= elapsed * 3 + .15
        self.previous = (record.ident, position, now)
        return Track(source=SOURCE, title=title, artist=artist, album=record.album,
                     duration=record.duration, position=min(position, record.duration),
                     playing=playing, observed=now, recording_id=record.ident,
                     sampled_position=True, cover_url=record.cover_url)
