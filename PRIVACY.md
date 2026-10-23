# Privacy

CPU, RAM and available GPU readings are processed locally and rendered to the
preview/USB display. The program has no analytics or crash-upload service and
opens no listening port. It does not upload those hardware readings.

Weather defaults to automatic IP-based location; an existing manual city is preserved.
City search sends the entered city name to Open-Meteo's
geocoding service. Selected city coordinates are sent to Open-Meteo for forecasts.
Automatic location contacts ipwho.is; the provider observes
the connection's public IP and returns approximate city coordinates. Automatic
mode can repeat this lookup on refresh (approximately every ten minutes).
These HTTPS services naturally see network connection information. No GPS is used.

Selected city/coordinates, language and display settings are saved locally.
Disable weather to stop periodic weather/location requests. Network service
terms and availability may change; no credentials are embedded.

Providers: https://open-meteo.com/ and https://ipwho.is/ .


## Optional music mode

When enabled, music mode reads Windows media-session metadata and analyzes the default speaker/headphone output in memory. This can include sounds from other applications. It does not open the microphone, save recordings or upload audio. Disabling music mode stops these providers.

Online lyrics default to enabled and run only while music mode is enabled. Existing disabled or older-version preferences remain disabled. Recognized QQ Music, NetEase or Kugou players first query that service. If no timed match is obtained, the remaining services and LRCLIB are queried concurrently; the first matching timed lyrics are used. Unknown players use these metadata-based services directly. QQ sends the title to c.y.qq.com for public search suggestions and matching song identifiers to u.y.qq.com for metadata, then uses c.y.qq.com for LRC. NetEase sends title/artist and matched song identifiers to music.163.com. Kugou sends title/artist/duration and the selected public lyric identifier to lyrics.kugou.com. LRCLIB receives title/artist/album/duration at https://lrclib.net. Already-running losing requests may finish within their HTTP timeouts, but cannot replace the selected result. These providers observe connection information; their availability and coverage may change. No music-account credentials are accessed. Imported LRC files are saved locally for their matching track. Media artwork is retained only in bounded memory caches.

## Automatic program updates

Packaged Windows programs check the public Kinkairy/rio-system-monitor GitHub Releases endpoint after startup and every six hours. A newer full EXE is downloaded over HTTPS from that repository's Release assets and checked against the asset SHA-256 and size before staging under the local configuration directory. It replaces the current executable only after normal program exit; the next launch uses the new version. Failed checks/downloads retain the existing program. No GitHub login or token is used. GitHub and its download CDN observe connection information, but no hardware readings, songs, audio or user configuration are sent for updates. Source runs and UI capture/test modes do not auto-update.
