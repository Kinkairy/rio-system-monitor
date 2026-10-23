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


def lookup_platform(track):
    from .lyrics import parse_lrc
    player=identify_player(track.source)
    if not player:return (), 'unsupported_source'
    if not track.title or not track.artist or track.duration<=0:return (), 'insufficient_metadata'
    query=track.title+' '+track.artist
    try:
        if player=='qq':
            payload={'comm':{'ct':19,'cv':1859,'uin':'0'},'req':{'module':'music.search.SearchCgiService','method':'DoSearchForQQMusicDesktop','param':{'query':query,'num_per_page':10,'page_num':1,'search_type':0}}}
            data=request_json('https://u.y.qq.com/cgi-bin/musicu.fcg',referer='https://y.qq.com/',json_body=payload)
            result=data.get('req',{})
            if data.get('code')!=0 or result.get('code')!=0:return (), 'provider_error'
            candidates=[]
            for item in result.get('data',{}).get('body',{}).get('song',{}).get('list',[])[:10]:
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
        else:
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
        rows=parse_lrc(text)
        return rows,'ready' if rows else 'no_timed_lyrics'
    except Exception:return (), 'provider_error'
