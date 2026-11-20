import json

from rio_monitor.music import netease
from rio_monitor.music.lyrics import lookup
from rio_monitor.music.netease import SOURCE, parse_title, metadata_track, append_fallback, choose_session
from rio_monitor.music.netease_timing import PlaybackQueue
from rio_monitor.music.platforms import Candidate
from rio_monitor.music.state import Track, select_session, AutomaticMusicView


def test_strict_metadata():
    assert parse_title('奇妙能力歌（cover陈粒） - 任然') == ('奇妙能力歌（cover陈粒）', '任然')
    for text in ('网易云音乐', '网易云音乐 - 任然', 'A - B - C', ' - B', 'A - ', 'A\n - B', 'x'*513):
        assert parse_title(text) is None


def test_no_audio_ambiguity_and_no_fabricated_time():
    assert metadata_track(['A - B'], False, 10) is None
    assert metadata_track(['A - B', 'C - D'], True, 10) is None
    assert metadata_track(['网易云音乐'], True, 10) is None
    track = metadata_track(['A - B', 'A - B'], True, 10)
    assert track.title == 'A' and track.artist == 'B'
    assert not track.playing and track.duration == 0 and track.position is None
    assert track.position_at(10) is None and track.position_at(100) is None


def test_native_and_manual_priority():
    track = metadata_track(['A - B'], True, 10)
    native = [('cloudmusic.exe', False, object())]
    assert append_fallback(native, track) is native
    edge = [('MSEdge', True, object())]
    added = append_fallback(edge, track)
    assert select_session(added)[0] == 'MSEdge'
    assert choose_session(added, '', SOURCE)[0] == 'MSEdge'
    assert choose_session(added, SOURCE, SOURCE)[0] == SOURCE
    assert select_session(added, SOURCE)[0] == SOURCE
    assert select_session(added, 'missing') is None
    assert select_session(append_fallback([], None), SOURCE) is None


def test_audio_only_view_and_expiry():
    track = metadata_track(['A - B'], True, 10)
    view = AutomaticMusicView()
    snap = dict(enabled=True, status='audio_only', track=track)
    assert view.select(snap, 10)
    assert not AutomaticMusicView().select(snap, 14)
    snap['status'] = 'no_session'
    view.select(snap, 11)
    assert not view.select(snap, 42)


def test_sampled_desktop_position_play_pause_seek_and_track_change(monkeypatch):
    player = netease.NetEasePlayback()
    now = 10
    position = 24.0
    name = 'A'
    audible = {123}
    record = Candidate('40', 'A', ('B',), 'Album', 200)
    monkeypatch.setattr(netease.time, 'monotonic', lambda: now)
    monkeypatch.setattr('rio_monitor.music.coreaudio.active_cloudmusic_pids', lambda: audible)
    monkeypatch.setattr(netease, '_windows', lambda pids: [(123, name + ' - B')] if 123 in pids else [])
    monkeypatch.setattr(player.clock, 'read', lambda pid: position)
    monkeypatch.setattr(player.queue, 'find', lambda title, artist: record if record.title == title else None)

    assert player.observe().recording_id == '40'
    now, position = 10.5, 24.5
    playing = player.observe()
    assert playing.playing and playing.position_at(10.9) == 24.5
    assert playing.position_at(14) is None
    now, audible = 11, set()
    paused = player.observe()
    assert not paused.playing and paused.position == 24.5
    assert append_fallback([], paused)[0][1] is False
    view = AutomaticMusicView()
    assert view.select(dict(enabled=True, status='ready', track=playing), 10.5)
    assert view.select(dict(enabled=True, status='ready', track=paused), 11)
    assert not view.select(dict(enabled=True, status='ready', track=paused), 41)

    now, position = 12, 123.4
    seek = player.observe()
    assert not seek.playing and seek.position == 123.4
    now, position, audible = 12.5, 123.9, {123}
    assert player.observe().playing

    now, name, position = 13, 'C', .3
    changing = player.observe()
    assert changing.title == 'C' and changing.position is None and not changing.recording_id
    now, position, record = 14, 1.3, Candidate('41', 'C', ('B',), 'Different album', 225)
    changed = player.observe()
    assert changed.position == 1.3 and changed.key != playing.key
    now, position = 14.5, 500
    assert player.observe().position is None


def test_queue_requires_unique_current_recording_and_updates(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    path = tmp_path / 'NetEase' / 'CloudMusic' / 'webdata' / 'file' / 'playingList'
    path.parent.mkdir(parents=True)
    item = {'track': {'id': '40', 'name': 'A', 'duration': 200_500,
                       'artists': [{'name': 'M'}, {'name': 'N'}],
                       'album': {'name': '盤','picUrl':'http://p4.music.126.net/same.jpg'}}}
    queue = PlaybackQueue()
    path.write_text(json.dumps({'list': [item, item]}), encoding='utf-8')
    expected = Candidate('40', 'A', ('M', 'N'), '盤', 200.5)
    assert queue.find('A', 'M/N') == expected
    assert queue.find('A', 'M/N').cover_url == 'https://p4.music.126.net/same.jpg?param=384y384'
    assert queue.find('A', 'M / N') == expected
    assert queue.find('A', 'M') is None
    other = {'track': dict(item['track'], id='500')}
    path.write_text(json.dumps({'list': [item, other]}), encoding='utf-8')
    assert queue.find('A', 'M/N') is None
    path.write_text('{', encoding='utf-8')
    assert queue.find('A', 'M/N') is None


def test_lyrics_for_verified_id_use_existing_netease_endpoint(monkeypatch):
    calls = []

    def request(url, *args, **kwargs):
        calls.append(url)
        return {'code': 200, 'lrc': {'lyric': '[00:01.00]hello\n[00:02.00]there'}}

    monkeypatch.setattr('rio_monitor.music.platforms.request_json', request)
    track = Track(source=SOURCE, title='A', artist='B', duration=200, recording_id='12345')
    rows, status = lookup(track)
    assert status == 'ready' and [row.text for row in rows] == ['hello', 'there']
    assert len(calls) == 1 and calls[0].startswith('https://music.163.com/api/song/lyric?id=12345&')


def test_hidden_tray_player_uses_only_the_verified_main_window(monkeypatch):
    from types import SimpleNamespace

    records = {
        1: (101, False, 'OrpheusBrowserHost', 'Song - Artist'),
        2: (101, False, 'icon', 'Stale - Artist'),
        3: (404, False, 'OrpheusBrowserHost', 'Foreign - Artist'),
        4: (101, True, 'OldClientClass', 'Visible - Artist'),
    }

    def visits(callback, param):
        for hwnd in records:
            callback(hwnd, param)
        return True

    def process(hwnd, out):
        out._obj.value = records[hwnd][0]

    def copy_title(hwnd, buffer, count):
        buffer.value = records[hwnd][3]

    def copy_class(hwnd, buffer, count):
        buffer.value = records[hwnd][2]

    fake = SimpleNamespace(
        EnumWindows=visits,
        GetWindowThreadProcessId=process,
        IsWindowVisible=lambda hwnd: records[hwnd][1],
        GetClassNameW=copy_class,
        GetWindowTextLengthW=lambda hwnd: len(records[hwnd][3]),
        GetWindowTextW=copy_title,
    )
    monkeypatch.setattr(netease, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(netease.c, 'WinDLL', lambda *args, **kwargs: fake, raising=False)
    monkeypatch.setattr(netease.c, 'WINFUNCTYPE', lambda *args: lambda fn: fn, raising=False)

    assert netease._windows({101}) == [(101, 'Song - Artist'), (101, 'Visible - Artist')]


def test_album_art_accepts_only_the_netease_image_host():
    from rio_monitor.music.netease_timing import album_cover_url

    assert not album_cover_url({'picUrl': 'https://example.com/cover.jpg'})
    assert not album_cover_url({'picUrl': 'https://p1.music.126.net@example.com/cover.jpg'})
    assert album_cover_url({'cover': 'http://p3.music.126.net/cover.jpg'}) == (
        'https://p3.music.126.net/cover.jpg?param=384y384'
    )


def test_native_netease_poll_keeps_or_recovers_the_selected_song(monkeypatch):
    import asyncio
    import datetime
    import sys
    from types import SimpleNamespace

    from rio_monitor.music.windows import MediaSessions

    profiles = (
        # A complete media session takes priority over the desktop adapter.
        (190, 44, 'Album', 44, 190, False),
        # The published position is valid even when the end timestamp is zero.
        (0, 58, 'Album', 58, 200, False),
        # Blank timing is recovered from the verified clock for the same song.
        (0, 0, 'Album', 30, 200, True),
        (0, 0, 'Album', 75, 200, True),
        # A different edition must not inherit the desktop playback clock.
        (0, 0, 'Other album', None, 0, False),
    )
    index = 0
    calls = []
    published = []

    async def properties():
        return SimpleNamespace(title='A', artist='B', album_title=profiles[index][2], thumbnail=None)

    def timeline():
        end, position, *_ = profiles[index]
        return SimpleNamespace(
            start_time=datetime.timedelta(0), end_time=datetime.timedelta(seconds=end),
            position=datetime.timedelta(seconds=position),
            last_updated_time=datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc),
        )

    session = SimpleNamespace(
        source_app_user_model_id='cloudmusic.exe', try_get_media_properties_async=properties,
        get_timeline_properties=timeline,
        get_playback_info=lambda: SimpleNamespace(playback_status=5 if index == 3 else 4),
    )

    async def request():
        return SimpleNamespace(get_sessions=lambda: [session])

    monkeypatch.setitem(sys.modules, 'winrt.windows.media.control', SimpleNamespace(
        GlobalSystemMediaTransportControlsSessionManager=SimpleNamespace(request_async=request),
    ))

    def publish(track, sources, status):
        nonlocal index
        published.append((track, sources, status))
        index += 1
        if index == len(profiles):
            provider.stop.set()

    provider = MediaSessions(publish, lambda: '')
    provider.netease.queue.find = lambda title, artist: Candidate('40', 'A', ('B',), 'Album', 200)

    def sample():
        import time
        calls.append(index)
        return Track(source=SOURCE, title='A', artist='B', album='Album', duration=200,
                     position=profiles[index][3], observed=time.monotonic(),
                     recording_id='40', sampled_position=True)

    provider.netease.observe = sample
    asyncio.run(provider.poll())

    assert calls == [2, 3]
    for profile, (track, sources, status) in zip(profiles, published, strict=True):
        _, _, album, position, duration, sampled = profile
        assert status == 'ready'
        assert sources == [{'id': 'cloudmusic.exe', 'label': 'cloudmusic.exe'}]
        assert track.key == ('cloudmusic.exe', 'A', 'B', album)
        assert (track.position, track.duration, track.sampled_position) == (position, duration, sampled)
    assert published[3][0].position_at(published[3][0].observed + 1) == 75


def test_native_timeline_does_not_use_unavailable_or_mismatched_clock(monkeypatch):
    playback = netease.NetEasePlayback()
    track = Track(source='cloudmusic.exe', title='A', artist='B', playing=True)
    record = Candidate('40', 'A', ('B',), 'Album', 200)
    monkeypatch.setattr(playback.queue, 'find', lambda title, artist: record)
    monkeypatch.setattr(playback, 'observe', lambda: Track(
        source=SOURCE, title='Different song', artist='B', duration=200,
        position=72, recording_id='99', sampled_position=True,
    ))
    assert playback.fill_native_timeline(track).position is None
    monkeypatch.setattr(playback, 'observe', lambda: None)
    assert playback.fill_native_timeline(track).position is None
