"""Own bounded background workers; never acquire audio before music mode is enabled."""
import threading,time,hashlib
from pathlib import Path
from dataclasses import replace
from .state import Track,Audio
from .lyrics import parse_lrc,lookup
from .windows import MediaSessions,Loopback

class Music:
    def __init__(self,cache,enabled=False,online=False,source='',start=True):
        self.cache=Path(cache);self.lock=threading.RLock();self.stop=threading.Event();self.wake=threading.Event()
        self.enabled=enabled;self.online=online;self.source=source;self.track=Track();self.audio=Audio();self.sources=[];self.status='off';self.rows=();self.lyric_status='off';self.generation=0;self.pending=None;self.requested=None
        self.workers=[];self.providers=[]
        if start:
            for fn in (self.manage,self.lyrics_loop):
                t=threading.Thread(target=fn,daemon=True);self.workers.append(t);t.start()
    def configure(self,enabled,online,source):
        with self.lock:
            if (enabled,online,source)==(self.enabled,self.online,self.source):return
            self.enabled,self.online,self.source=enabled,online,source;self.generation+=1;self.requested=None
            if not enabled:self.track=Track();self.audio=Audio();self.rows=();self.status='off';self.lyric_status='off'
            else:self.status='starting';self.queue_lyrics()
        self.wake.set()
    def preference(self):
        with self.lock:return self.source
    def queue_lyrics(self):
        if not self.track.title:return
        key=(self.track.key,round(self.track.duration),self.online)
        if self.requested==key:return
        self.requested=key;self.pending=(self.generation,self.track,self.online);self.lyric_status='loading';self.wake.set()
    def media_update(self,track,sources,status):
        with self.lock:
            if not self.enabled:return
            if track.key!=self.track.key:self.generation+=1;self.rows=();self.requested=None
            self.track,self.sources,self.status=track,sources,status;self.queue_lyrics()
    def audio_update(self,audio):
        with self.lock:
            if self.enabled:self.audio=audio
    def snapshot(self):
        with self.lock:return dict(track=self.track,audio=self.audio,rows=self.rows,status=self.status,lyric_status=self.lyric_status,sources=list(self.sources),enabled=self.enabled)
    def manage(self):
        media=audio=None
        try:
            while not self.stop.wait(.15):
                with self.lock:enabled=self.enabled
                if enabled and media is None:
                    media=MediaSessions(self.media_update,self.preference);audio=Loopback(self.audio_update);self.providers=[media,audio];media.start();audio.start()
                elif not enabled and media:
                    if media.close() and audio.close():media=audio=None;self.providers=[]
        finally:
            if media:media.close()
            if audio:audio.close()
    def local_path(self,track):return self.cache/(hashlib.sha256(repr(track.key).encode()).hexdigest()+'.lrc')
    def import_lrc(self,path):
        raw=Path(path).read_bytes()
        if len(raw)>1024*1024:raise ValueError('Lyrics file exceeds 1 MB')
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:text=raw.decode('gb18030')
        rows=parse_lrc(text)
        if not rows:raise ValueError('No timestamped LRC lines')
        with self.lock:
            if not self.track.title:raise ValueError('Play a song before importing lyrics')
            self.cache.mkdir(parents=True,exist_ok=True);self.local_path(self.track).write_text(text,encoding='utf-8');self.generation+=1;self.rows=rows;self.lyric_status='local';self.pending=None
    def lyrics_loop(self):
        while not self.stop.is_set():
            self.wake.wait(.5);self.wake.clear()
            with self.lock:job=self.pending;self.pending=None
            if not job:continue
            generation,track,online=job
            try:
                path=self.local_path(track)
                if path.is_file():rows=parse_lrc(path.read_text(encoding='utf-8'));status='local'
                elif online:rows,status=lookup(track)
                else:rows,status=(),'online_off'
            except Exception:rows,status=(),'lyrics_error'
            with self.lock:
                if self.enabled and generation==self.generation and track.key==self.track.key:self.rows,self.lyric_status=rows,status
    def close(self):
        self.enabled=False;self.stop.set();self.wake.set()
        for provider in self.providers:provider.stop.set()
        for worker in self.workers:worker.join(.2)
        return all(not worker.is_alive() for worker in self.workers) and all(not p.thread or not p.thread.is_alive() for p in self.providers)
