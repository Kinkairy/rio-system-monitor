"""LRC parsing, source-specific matching and optional LRCLIB fallback. No account tokens."""
from dataclasses import dataclass
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor,as_completed
import re,json,urllib.parse,urllib.request,urllib.error

# Threads start only when needed and are reused across songs; never grow per lookup.
_fallback_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='RIO-lyrics')

@dataclass(frozen=True)
class Lyric:
    time: float
    text: str

def parse_lrc(text):
    if len(text)>1024*1024:raise ValueError('Lyrics too large')
    offset=re.search(r'\[offset:([+-]?\d+)\]',text,re.I)
    shift=int(offset[1])/1000 if offset else 0
    rows=[]
    for line in text.splitlines():
        stamps=list(re.finditer(r'\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]',line))
        if not stamps:continue
        words=line[stamps[-1].end():].strip()[:1000]
        for stamp in stamps:
            minute,second,fraction=stamp.groups()
            if int(second)>=60:continue
            rows.append(Lyric(max(0,int(minute)*60+int(second)+(int(fraction)/10**len(fraction) if fraction else 0)+shift),words))
    return tuple(sorted(rows,key=lambda x:x.time)[:10000])

def current_lines(rows,position):
    if position is None or not rows:return ('','')
    index=bisect_right([r.time for r in rows],position)-1
    if index<0:return ('',rows[0].text)
    return rows[index].text,rows[index+1].text if index+1<len(rows) else ''

def lookup_lrclib(track):
    # Exact GET matching only: title/artist/album/duration sent after opt-in.
    if not track.title or not track.artist or track.duration<=0:return (), 'insufficient_metadata'
    args=dict(track_name=track.title,artist_name=track.artist,album_name=track.album,duration=round(track.duration))
    request=urllib.request.Request('https://lrclib.net/api/get?'+urllib.parse.urlencode(args),headers={'User-Agent':'RIO-System-Monitor/1.0 (https://github.com/Kinkairy/rio-system-monitor)'})
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('Lyrics response too large')
        data=json.loads(raw)
        if abs(float(data.get('duration',0))-track.duration)>3:return (), 'not_found'
        normalize=lambda s:' '.join(str(s).casefold().split())
        if normalize(data.get('trackName'))!=normalize(track.title) or normalize(data.get('artistName'))!=normalize(track.artist):return (), 'not_found'
        if data.get('instrumental'):return (), 'instrumental'
        rows=parse_lrc(data.get('syncedLyrics') or '')
        return rows,'ready' if rows else 'no_timed_lyrics'
    except urllib.error.HTTPError as exc:
        return ((),'not_found') if exc.code==404 else ((),'network_error')
    except Exception:return (), 'network_error'


def lookup(track):
    from .platforms import identify_player,lookup_platform
    if not track.title or not track.artist or track.duration<=0:return (), 'insufficient_metadata'
    player=identify_player(track.source);statuses=[]
    if player:
        rows,status=lookup_platform(track,player)
        if rows:return rows,status
        statuses.append(status)
    futures=[_fallback_pool.submit(lookup_lrclib,track)]
    futures.extend(_fallback_pool.submit(lookup_platform,track,name) for name in ('qq','netease','kugou') if name!=player)
    try:
        for future in as_completed(futures):
            try:rows,status=future.result()
            except Exception:rows,status=(),'provider_error'
            if rows:return rows,status
            statuses.append(status)
    finally:
        for future in futures:future.cancel()
    for status in ('instrumental','provider_error','network_error','no_timed_lyrics'):
        if status in statuses:return (),status
    return (), 'not_found'
