"""HTTPS weather worker; network location is enabled by default in Settings.
No stored IP, GPS, credentials or port listener.
"""
import json,math,time,threading,urllib.request,urllib.parse,datetime
from .weather import WeatherReading

def fetch_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'RIO-Monitor/0.2'})
    with urllib.request.urlopen(request,timeout=8) as response:
        if not response.geturl().startswith('https://'):raise ValueError('Insecure redirect')
        data=response.read(262145)
        if len(data)>262144:raise ValueError('Response too large')
        return json.loads(data)

def kind_for(code):
    if code in (0,1):return 'sun'
    if code in (2,3):return 'cloud'
    if code in (45,48):return 'fog'
    if code in (51,53,55,56,57,61,63,65,66,67,80,81,82):return 'rain'
    if code in (71,73,75,77,85,86):return 'snow'
    if code in (95,96,99):return 'thunder'
    return None

def coordinates(data):
    lat,lon=float(data['latitude']),float(data['longitude'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Invalid coordinates')
    return round(lat,2),round(lon,2)

def cities(name,fetch=fetch_json):
    url='https://geocoding-api.open-meteo.com/v1/search?'+urllib.parse.urlencode({'name':name,'count':5,'language':'en','format':'json'})
    return fetch(url).get('results',[])

class WeatherWorker:
    def __init__(self,settings,fetch=fetch_json):
        self.settings=settings;self.fetch=fetch;self.reading=None;self.status='Weather off';self.location=None
        self.stop=threading.Event();self.wake=threading.Event();self.lock=threading.Lock();self.generation=0
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def configure(self,settings,location=None):
        with self.lock:
            self.settings=settings;self.location=location;self.reading=None;self.generation+=1
        self.wake.set()
    def refresh(self):self.wake.set()
    def run(self):
        while not self.stop.is_set():
            with self.lock:s=self.settings;loc=self.location;generation=self.generation
            reading=None;status='Weather off'
            try:
                if s.weather_mode=='auto':
                    geo=self.fetch('https://ipwho.is/?fields=success,city,region,country,latitude,longitude')
                    if geo.get('success') is not True:raise ValueError('IP location unavailable')
                    lat,lon=coordinates(geo);label=', '.join(str(geo.get(k,'')) for k in ('city','region','country') if geo.get(k))
                    loc=(lat,lon,label)
                elif s.weather_mode=='manual' and loc is None:
                    # Saved city is the exact selected unique label with coordinates.
                    saved=json.loads(s.city);lat,lon=coordinates(saved);loc=(lat,lon,str(saved['label']))
                if s.weather_mode!='off':
                    if loc is None:raise ValueError('Select a city')
                    url='https://api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode({'latitude':loc[0],'longitude':loc[1],'current':'temperature_2m,weather_code','temperature_unit':'celsius','timeformat':'unixtime','timezone':'UTC'})
                    data=self.fetch(url);current=data['current'];v=current['temperature_2m'];stamp=float(current['time'])
                    if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not -100<=v<=70:raise ValueError('Invalid temperature')
                    age=time.time()-stamp
                    if not -300<=age<=1800:raise ValueError('Weather data is stale')
                    reading=WeatherReading(kind_for(current.get('weather_code')),v,time.monotonic()-max(0,age),'Open-Meteo model')
                    status=loc[2]+' · Open-Meteo'
            except Exception as exc:status='Weather unavailable: '+str(exc)
            with self.lock:
                if generation==self.generation:self.reading=reading;self.status=status;self.location=loc
            self.wake.wait(600);self.wake.clear()
    def close(self):self.stop.set();self.wake.set();self.thread.join(timeout=.2)
