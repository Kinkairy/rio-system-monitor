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

Online lyrics are a separate opt-in. Enabling them sends song title, artist, album and duration to https://lrclib.net to match timestamped lyrics. No music-account credentials are accessed. Imported LRC files are saved locally for their matching track. Media artwork is retained only in bounded memory caches.
