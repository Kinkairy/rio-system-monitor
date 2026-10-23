"""Best-effort unauthenticated lyric adapters. Independent implementation, no LX code.

These are undocumented service endpoints, not supported public API contracts.
Fail closed on ambiguous metadata; never request audio or access account cookies.
"""
import base64,html,json,re,unicodedata,urllib.parse,urllib.request
from dataclasses import dataclass


def identify_player(source):
    value=str(source).replace('\\','/').casefold()
    name=value.rsplit('/',1)[-1]
    if name in ('qqmusic','qqmusic.exe') or re.match(r'^tencent\.qqmusic_[a-z0-9]+!',name):return 'qq'
    if name in ('cloudmusic','cloudmusic.exe','neteasecloudmusic','neteasecloudmusic.exe') or re.match(r'^netease\.cloudmusic_[a-z0-9]+!',name):return 'netease'
    if name in ('kugou','kugou.exe','kugoumusic','kugoumusic.exe'):return 'kugou'
    return None  # Browsers, LX and unknown app IDs must not be guessed.


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC',html.unescape(str(value))).casefold().split())


@dataclass(frozen=True)
class Candidate:
    ident: str
    title: str
    artists: tuple
    album: str
    duration: float


def match_candidate(track,candidates):
    if not track.title or not track.artist or track.duration<=0:return None
    matches={}
    for item in candidates:
        if normalized(item.title)!=normalized(track.title):continue
        artist=normalized(track.artist)
        joins={normalized(sep.join(item.artists)) for sep in (' / ','、',', ',' & ','; ','/')}
        if artist not in joins:continue
        if abs(item.duration-track.duration)>3:continue
        if track.album and normalized(item.album)!=normalized(track.album):continue
        matches[item.ident]=item
    return next(iter(matches.values())) if len(matches)==1 else None


def request_json(url,form=None,referer=None,json_body=None):
    headers={'User-Agent':'RIO-System-Monitor/1.0'}
    if referer:headers['Referer']=referer
    data=None
    if json_body is not None:
        data=json.dumps(json_body).encode();headers['Content-Type']='application/json'
    elif form is not None:
        data=urllib.parse.urlencode(form).encode();headers['Content-Type']='application/x-www-form-urlencoded'
    request=urllib.request.Request(url,data=data,headers=headers)
    with urllib.request.urlopen(request,timeout=4) as response:raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Response too large')
    result=json.loads(raw)
    if not isinstance(result,dict):raise ValueError('Invalid response')
    return result


def lookup_platform(track,player=None):
    from .lyrics import parse_lrc
    player=player or identify_player(track.source)
    if player not in ('qq','netease','kugou'):return (), 'unsupported_source'
    if not track.title or not track.artist or track.duration<=0:return (), 'insufficient_metadata'
    query=track.title+' '+track.artist
    try:
        if player=='qq':
            suggestions=request_json('https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg?'+urllib.parse.urlencode(dict(key=track.title,format='json',is_xml=0)),referer='https://y.qq.com/')
            if suggestions.get('code')!=0:return (), 'provider_error'
            mids=list(dict.fromkeys(str(s.get('mid','')) for s in suggestions.get('data',{}).get('song',{}).get('itemlist',[])[:10] if re.fullmatch('[A-Za-z0-9]{1,64}',str(s.get('mid','')))))
            if not mids:return (), 'not_found'
            payload={mid:{'module':'music.pf_song_detail_svr','method':'get_song_detail_yqq','param':{'song_mid':mid}} for mid in mids}
            details=request_json('https://u.y.qq.com/cgi-bin/musicu.fcg',referer='https://y.qq.com/',json_body=payload)
            if details.get('code')!=0:return (), 'provider_error'
            if any(details.get(mid,{}).get('code')!=0 for mid in mids):return (), 'provider_error'
            songs=[details[mid].get('data',{}).get('track_info',{}) for mid in mids]
            candidates=[]
            for item in songs[:10]:
                ident=str(item.get('mid',''))
                if not re.fullmatch('[A-Za-z0-9]{1,64}',ident):continue
                # QQ publishes display aliases in SMTC, but also supplies the raw names.
                for field in ('name','title'):
                    artists=tuple(s.get(field) or s.get('name','') for s in item.get('singer',[]))
                    candidates.append(Candidate(ident,item.get('title') or item.get('name',''),artists,item.get('album',{}).get('name',''),float(item.get('interval',0))))
            matched=match_candidate(track,candidates)
            if not matched:return (), 'not_found'
            data=request_json('https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?'+urllib.parse.urlencode(dict(songmid=matched.ident,format='json',nobase64=1)),referer='https://y.qq.com/')
            if data.get('code')!=0:return (), 'provider_error'
            text=html.unescape(data.get('lyric') or '')
            # Some versions ignore nobase64. Accept only regular UTF-8 LRC.
            if '[' not in text:
                text=base64.b64decode(text,validate=True).decode('utf-8')
        elif player=='netease':
            data=request_json('https://music.163.com/api/cloudsearch/pc',dict(s=query,type=1,limit=10,offset=0),referer='https://music.163.com/')
            if data.get('code')!=200:return (), 'provider_error'
            result=data.get('result')
            if not isinstance(result,dict):return (), 'provider_error'
            candidates=[]
            for item in result.get('songs',[])[:10]:
                ident=str(item.get('id',''))
                if not re.fullmatch('[0-9]{1,20}',ident):continue
                candidates.append(Candidate(ident,item.get('name',''),tuple(s.get('name','') for s in item.get('ar',[])),item.get('al',{}).get('name',''),float(item.get('dt',0))/1000))
            matched=match_candidate(track,candidates)
            if not matched:return (), 'not_found'
            data=request_json('https://music.163.com/api/song/lyric?'+urllib.parse.urlencode(dict(id=matched.ident,lv=-1,kv=-1,tv=-1)),referer='https://music.163.com/')
            if data.get('code')!=200:return (), 'provider_error'
            text=data.get('lrc',{}).get('lyric') or ''
        else:
            data=request_json('https://lyrics.kugou.com/search?'+urllib.parse.urlencode(dict(ver=1,man='yes',client='pc',keyword=query,duration=round(track.duration*1000))))
            if data.get('status')!=200:return (), 'provider_error'
            matches=[item for item in data.get('candidates',[])[:10] if normalized(item.get('song',''))==normalized(track.title) and normalized(item.get('singer',''))==normalized(track.artist) and abs(float(item.get('duration',0))/1000-track.duration)<=3]
            if not matches:return (), 'not_found'
            # Multiple contributions can describe the same timed song; prefer closest duration.
            matched=min(matches,key=lambda item:abs(float(item.get('duration',0))/1000-track.duration))
            data=request_json('https://lyrics.kugou.com/download?'+urllib.parse.urlencode(dict(ver=1,client='pc',id=matched['id'],accesskey=matched['accesskey'],fmt='lrc',charset='utf8')))
            if data.get('status')!=200:return (), 'provider_error'
            text=base64.b64decode(data.get('content') or '',validate=True).decode('utf-8-sig')
        rows=parse_lrc(text)
        return rows,'ready' if rows else 'no_timed_lyrics'
    except Exception:return (), 'provider_error'
