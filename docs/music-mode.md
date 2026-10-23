# Music mode (Windows, opt-in)

## Architecture and privacy

Music mode is a separate live renderer and does not replace monitoring or screen-storage ownership. Enable it from Settings > Music mode, or the tray. Disabling it stops media/audio acquisition. No microphone is opened. WASAPI loopback captures the default output-device mix in memory, including unrelated app sounds. Audio is never saved, transmitted or sent to lyric services. Device changes reopen the loopback stream. Exclusive/DRM playback can be unavailable.

SMTC supplies title/artist/album, thumbnail, playback state and timeline when published by the selected player. Auto selection keeps the previous playing session to prevent unnecessary switches. An explicit selected session never silently falls back to another app. Timeline missing or stale: do not invent lyric synchronization. Artwork decode is bounded and cached. Empty artwork uses a neutral RIO record, not a fictitious album.

LRCLIB lyric lookup is separately opt-in and sends title, artist, album and duration via HTTPS to lrclib.net/api/get. No accounts, cookies or audio are sent. Exact title/artist and duration checks reject ambiguous mismatches. LRC files can be imported for the current track; stored under the user's config directory keyed by track identity. Late network replies are discarded after track changes, disable, or local imports. Source-specific QQ/NetEase lyric adapters now run before LRCLIB after renewed consent; see below. No QRC decryption, account access, third-party executable plugins or music download/playback source are included.

## Rendering

Approved split layout: original private RIO badge, rotating 188px cover on a 222px record, 74px yellow center label and 6px spindle hole. Left/right segmented upper gauges light together with different palettes. Bottom columns use full vertical rainbow color and damped spring motion; low bands map to the center and high bands outward. Real spectrum magnitudes drive heights, never synthetic sine waves. Audio stale >350ms decays to zero. No claims of BPM-perfect beat detection.

Track change: record exits left in 260ms. Four lyric display rows exit right in 180ms each, staggered 40ms (300ms total). New content enters after 380ms. Fonts use private RIOPixel when supplied; otherwise existing Born2bSporty fallback. CJK text uses Windows Microsoft YaHei or explicitly supplied compatible font. Fonts and screenshots must not enter the public source repo.

## Compatibility research (2026-10-23)

These are source/documentation findings, NOT validation of RIO against every installed player version:

- QQ Music: SMTC documented by integration projects; song metadata and timeline need installed-version tests.
- NetEase Cloud Music: UWP/desktop builds differ; some desktop versions need an SMTC plugin. No plugin is installed by RIO.
- Kugou: listed by SMTC integration projects; exact fields/version still need tests.
- Kuwo: insufficient authoritative evidence for direct SMTC compatibility; pending local verification. Loopback audio can work without metadata.
- Spotify: SMTC integrations available; timing fidelity varies by release.
- Apple Music Windows: SMTC integrations available; timeline instability reported by Lyricify. Do not promise accurate seek synchronization without tests.
- Browser music / YouTube Music: depends on website Media Session metadata and browser OS integration. Browser app ID is not a reliable music-service identity.
- Foobar2000/local players: depends on SMTC integration/plugin and file tags.
- LX Music: separate platform lyric adapters and user-defined playback sources. Official local Open API is a possible future adapter, not implemented here.

All players need an independent timed lyric source. Song metadata availability does not imply lyrics exist. LRCLIB coverage, especially alternate/live versions, is not guaranteed.

Sources:
- https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording
- https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager
- https://docs.lyricify.app/en/lyricify-fusion/supported-apps/
- https://github.com/Lyricify/Lyricify
- https://github.com/GotKiCry/QQMusicMonitor/blob/main/Project.md
- https://developer.mozilla.org/en-US/docs/Web/API/MediaSession
- https://github.com/tranxuanthang/lrclib
- https://github.com/s0d3s/PyAudioWPatch
- https://lxmusic.toside.cn/desktop/open-api
- https://lxmusic.toside.cn/desktop/custom-source

## Validation boundary

Unit tests exercise silence/stale audio, stereo phase cancellation, LRC parsing/seeking, explicit source selection, opt-in boundaries, local imports, wrong lyric-version rejection, missing art, paused rotation and transitions. Linux offscreen QML validation is not Windows hardware validation. Windows SMTC/loopback, headphone switching, minimized/tray behavior, dependency bundling and USB sustained frame rate still require Windows tests. No new deployment or driver installation is performed by this change.

## Source-specific lyrics (2026-10-23)

Order: explicit locally imported LRC, recognized player's platform, LRCLIB fallback, then no-lyrics state. Known QQMusic.exe / cloudmusic.exe names and supported package-ID patterns are mapped conservatively. Unknown IDs, browsers and LX are not assumed to be QQ or NetEase; use generic fallback. This recognizes a published session, not merely a running process. App identity support is version dependent.

Independent implementation uses QQ unauthenticated search and regular LRC endpoints on c.y.qq.com; NetEase cloudsearch and regular LRC endpoints on music.163.com. These are undocumented platform interfaces, not stable official developer APIs. No LX code, signature algorithm, cookies, credentials, QRC decoder or playback URL resolution is copied. At most 10 candidates, exact normalized title/artist, duration within 3 seconds, album equality when available, and one unambiguous song ID are required. Mismatches and network/schema failures fall back instead of guessing. Query timeout is 4 seconds per platform request; responses capped at 1 MiB; no repeated platform retry loop.

Existing users must re-enable online lyrics after reading the new provider disclosure (consent version 2). Real endpoint probes verify only the tested request/data shape, not every song or installed client. Windows SMTC compatibility still requires local tests.

References: Microsoft SourceAppUserModelId documentation and LX platform adapter architecture: https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.sourceappusermodelid and https://github.com/lyswhut/lx-music-desktop/tree/master/src/renderer/utils/musicSdk .
