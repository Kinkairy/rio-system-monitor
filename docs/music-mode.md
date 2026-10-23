# Music mode (Windows, opt-in)

## FIX-20261023-QQ-LYRICS: failed online lyric lookup

Owner report on 2026-10-23: lyrics never appear in the running `rc0.1` application. Verified base: clean source `0766054ba3e73b91dfc126572edd8f066f89de9f`; the running Downloads executable has SHA-256 `04f5d5a48083c2eaac88c94ace3a8ecce3438da92d4bc85ec15ab258432b0c8a`. Music mode and online lyrics are enabled. Windows publishes a playing QQMusic.exe session with complete title/artist/album/duration and a usable timeline.

Reproduction: the legacy QQ `client_search_cp` search failed with HTTP 500; the LRCLIB fallback returned HTTP 503. The unsigned QQ MusicU desktop search returned a unique title/artist/album/duration match, and the existing regular LRC endpoint returned 59 timed rows for that match. Current code also suppresses subsequent queries for the same track after a transient error.

Planned scope: replace only the QQ search request/parser with the verified MusicU shape, keeping the existing lyric endpoint and exact matching. Retry a transient query failure once after five seconds in the existing lyric worker; track changes, disable, shutdown or local imports cancel that retry. Distinguish connection errors from an absent match in existing status text. No audio, renderer layout, output pacing, platform identity or account-access change. Retain the published `rc0.1` tag and current running executable; prepare a local corrected build and follow the owner's existing instruction to keep the public source current. Update the existing version note and privacy text for this same change; private assets and executables remain local.

Acceptance: exercise the real selected player and lyric provider without USB writes or changing playback/settings; check that actual lyrics reach the existing controller and renderer. Run the affected existing tests plus focused request/retry regressions, build and self-test the corrected executable, verify private assets remain excluded, and compare the final diff with this scope. AMF `project_show(rio-system-monitor)` again returned `not_found`; this entry does not claim AMF registration.

### Results

The first GET-only candidate passed mocked search fixtures but failed the real controller check. It was replaced by JSON POST, and the corrected request, affected tests and final scope were checked again. Using the earlier captured QQ media metadata and the real online provider, the actual lyric worker reached `ready` with 59 timed rows; the existing renderer displayed nonempty synchronized lyric lines, visually checked in a local frame. A later live media read observed a different instrumental track; its direct QQ LRC response contained only the pure-music marker. These checks do not claim every song has timed lyrics or that every player metadata alias matches.

The full corrected-source suite passed: 160 tests, no skips, 17.909 seconds. Three focused regressions were added for the JSON POST contract, bounded retry, and cancellation by track change/disable/local import/shutdown; the existing QQ success fixture was updated to the real search response shape. Matching constraints and all rendering/output behavior remain as planned. No account credentials, signatures, music downloads or audio transmission were introduced.

The Windows build and standard packaged UI startup/capture passed (exit 0, empty stderr). The broader packaged UI self-test hit the same tray-menu visibility assertion on this desktop in two attempts; those test instances were stopped, and no tray code was changed to satisfy that unrelated check. The original running application was retained. The local corrected executable is `RIO-System-Monitor-rc0.1-lyrics-fix.exe`, 108647353 bytes, SHA-256 `60fd2a48886eb66c98a27f1e328dd90de570550c6bfd13f5d5e9a1be22a4ef3c`. Actual use of this corrected build on the physical screen remains for the owner to confirm. Private assets/executables are excluded from the public update. Cleanup of the new local build outputs was rejected by the local execution policy, including a second attempt restricted to explicit absolute paths (`blocked by policy`); those ignored files remain local and are not part of the source commit.

## Architecture and privacy

Music mode is a separate live renderer and does not replace monitoring or screen-storage ownership. Enable Music appreciation with the shared switch directly in the main settings window. The tray remains exactly Exit, Settings and Start at login; no music items are added. The display enters the music view when the selected player starts playing. After pause or stop it keeps that view for 30 continuous seconds, then returns to monitoring; resuming playback cancels the countdown. Turning the switch off returns immediately and stops media/audio acquisition. A missing/stale player session also expires the music view, while unrelated output sounds alone do not trigger it. No microphone is opened. WASAPI loopback captures the default output-device mix in memory, including unrelated app sounds. Audio is never saved, transmitted or sent to lyric services. Device changes reopen the loopback stream. Exclusive/DRM playback can be unavailable.

SMTC supplies title/artist/album, thumbnail, playback state and timeline when published by the selected player. Auto selection keeps the previous playing session to prevent unnecessary switches. An explicit selected session never silently falls back to another app. Timeline missing or stale: do not invent lyric synchronization. Missing or failed thumbnails retry every two seconds, with each local read limited to two seconds and 4 MiB. A successful cover is retained for the same track; a different track clears it immediately. Artwork decode is bounded and cached. Empty artwork uses a neutral RIO record, not a fictitious album.

Online lyrics default to enabled, but no lookup runs before music mode is enabled. Existing explicit opt-outs remain off. LRCLIB fallback sends title, artist, album and duration via HTTPS to lrclib.net/api/get. No accounts, cookies or audio are sent. Exact title/artist and duration checks reject ambiguous mismatches. LRC files can be imported for the current track; stored under the user's config directory keyed by track identity. Late network replies are discarded after track changes, disable, or local imports. Source-specific QQ/NetEase lyric adapters run before LRCLIB; see below. No QRC decryption, account access, third-party executable plugins or music download/playback source are included.

## Rendering

Approved split layout: original private RIO badge, rotating 188px cover on a 222px record, 74px yellow center label and 6px spindle hole. Left/right segmented upper gauges light together with different palettes. Bottom columns use full vertical rainbow color and damped spring motion; low bands map to the center and high bands outward. Real spectrum magnitudes drive heights, never synthetic sine waves. Audio stale >350ms decays to zero. No claims of BPM-perfect beat detection.

Monitor/music view changes use the same 550ms centered pop: scale from 72%, briefly overshoot to about 106%, and settle at 100%. A short initial opacity ramp avoids a hard first frame. Reversing during the effect continues from the last composed frame. No UI-thread wait or additional telemetry collection is involved. Song titles remain centered when they fit; long titles move back and forth within the 310px title area at 32px/second, holding one second at each end. Artist text is 14px instead of 10px.

The approved lyric layout and fonts remain: 19px first row, 23px second row and 13px next-lyric preview. Wrapping preserves every character; text remaining after the first row stays in the second row instead of being discarded. Each row is measured at its actual font size. Only an overflowing row scrolls left within its 125px area to reveal the end across the LRC time interval, with short holds at the beginning and end. Seeking selects the corresponding position and pause holds it. Fitting rows remain still; there is no pagination or font normalization.

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

Unit tests exercise silence/stale audio, stereo phase cancellation, LRC parsing/seeking, explicit source selection, opt-in boundaries, local imports, wrong lyric-version rejection, missing art, paused rotation and transitions, plus the 30-second pause/stop return and resume cancellation. Windows integration builds include the Foundation and Foundation.Collections WinRT projections as well as Media.Control and Storage.Streams; namespace imports alone do not verify a complete asynchronous SMTC query. No additional system driver is needed for these music providers. Live player metadata, actual loopback spectrum, headphone switching, tray interaction, dependency bundling and USB sustained frame rate are recorded separately from source tests.

## Source-specific lyrics (2026-10-23)

Order: explicit locally imported LRC, recognized player's platform, LRCLIB fallback, then no-lyrics state. Known QQMusic.exe / cloudmusic.exe names and supported package-ID patterns are mapped conservatively. Unknown IDs, browsers and LX are not assumed to be QQ or NetEase; use generic fallback. This recognizes a published session, not merely a running process. App identity support is version dependent.

Independent implementation uses QQ unauthenticated MusicU desktop search on u.y.qq.com and the regular LRC endpoint on c.y.qq.com; NetEase cloudsearch and regular LRC endpoints on music.163.com. These are undocumented platform interfaces, not stable official developer APIs. No LX code, signature algorithm, cookies, credentials, QRC decoder or playback URL resolution is copied. At most 10 candidates, exact normalized title/artist, duration within 3 seconds, album equality when available, and one unambiguous song ID are required. Mismatches and network/schema failures fall back instead of guessing. Query timeout is 4 seconds per platform request; responses capped at 1 MiB. A transient query error gets one retry after five seconds in the existing lyric worker, canceled by a changed track/configuration, local import or shutdown. An unavailable primary provider is not relabeled as a missing match merely because the fallback lacks that song.

New preferences enable the disclosed providers by default (provider-setting version 2); existing disabled or older-version preferences stay disabled. Real endpoint probes verify only the tested request/data shape, not every song or installed client. Windows SMTC compatibility still requires local tests.

References: Microsoft SourceAppUserModelId documentation and LX platform adapter architecture: https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.sourceappusermodelid and https://github.com/lyswhut/lx-music-desktop/tree/master/src/renderer/utils/musicSdk .
