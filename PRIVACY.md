# Privacy

CPU, RAM and available GPU readings are processed locally and rendered to the
preview/USB display. The program has no analytics or crash-upload service and
opens no listening port. It does not upload those hardware readings.

Weather starts disabled. City search sends the entered city name to Open-Meteo's
geocoding service. Selected city coordinates are sent to Open-Meteo for forecasts.
Automatic location/reset, after consent, contacts ipwho.is; the provider observes
the connection's public IP and returns approximate city coordinates. Automatic
mode can repeat this lookup on refresh (approximately every ten minutes).
These HTTPS services naturally see network connection information. No GPS is used.

Selected city/coordinates, language and display settings are saved locally.
Disable weather to stop periodic weather/location requests. Network service
terms and availability may change; no credentials are embedded.

Providers: https://open-meteo.com/ and https://ipwho.is/ .
