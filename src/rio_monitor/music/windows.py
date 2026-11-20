"""Windows-only providers. Lazy imports keep monitor mode independent."""
import asyncio,datetime,time,threading,sys,urllib.request
from dataclasses import replace
from .state import Track,Audio,Spectrum
from .platforms import identify_player
from .netease import SOURCE as NETEASE_FALLBACK, NetEasePlayback, append_fallback, choose_session, has_native_netease

MAX_COVER_BYTES = 4 * 1024 * 1024

def read_album_cover(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'RIO-System-Monitor/1.0'})
    with urllib.request.urlopen(request, timeout=2) as response:
        if not response.headers.get_content_type().startswith('image/'):
            return b''
        data = response.read(MAX_COVER_BYTES + 1)
    return data if len(data) <= MAX_COVER_BYTES else b''


async def read_cover(reference):
    if reference is None:return b''
    if isinstance(reference, str):
        return await asyncio.to_thread(read_album_cover, reference)
    from winrt.windows.storage.streams import DataReader
    stream=await reference.open_read_async()
    try:
        if stream.size>MAX_COVER_BYTES:return b''
        reader=DataReader(stream)
        try:
            count=await reader.load_async(int(stream.size));data=bytearray(count)
            reader.read_bytes(data)
            return bytes(data)
        finally:reader.close()
    finally:stream.close()

class CoverCache:
    """Retry late thumbnails without discarding a good cover for the same track."""
    def __init__(self):
        self.key = None
        self.data = b''
        self.retry_at = 0
        self.pending = None

    async def _read(self, reference):
        try:
            return await asyncio.wait_for(read_cover(reference), 2)
        except Exception:
            return b''

    async def get(self, key, reference, now):
        if key != self.key:
            if self.pending:
                self.pending.cancel()
            self.key = key
            self.data = b''
            self.retry_at = 0
            self.pending = None
        if self.pending and self.pending.done():
            self.data = self.pending.result()
            self.pending = None
        if not self.data and self.pending is None and now >= self.retry_at:
            self.retry_at = now + 2
            if isinstance(reference, str) and reference.startswith('https://'):
                self.pending = asyncio.create_task(self._read(reference))
            else:
                self.data = await self._read(reference)
        return self.data

def read_timeline(session, playing, allow_partial=False):
    duration = 0
    try:
        timeline = session.get_timeline_properties()
        start = timeline.start_time
        duration = max(0, (timeline.end_time - start).total_seconds())
        position = max(0, (timeline.position - start).total_seconds())
    except Exception:
        return duration, None
    if not duration and (not allow_partial or not position):
        return 0, None
    if playing:
        try:
            stamp = timeline.last_updated_time
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=datetime.timezone.utc)
            delta = (datetime.datetime.now(datetime.timezone.utc) - stamp).total_seconds()
            if 0 <= delta <= 5:
                position += delta
        except Exception:
            pass
    return duration, min(duration, position) if duration else position


class MediaSessions:
    def __init__(self,publish,preference):
        self.publish=publish
        self.preference=preference
        self.stop=threading.Event()
        self.thread=None
        self.netease=NetEasePlayback()
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='RIO-media');self.thread.start()
    def run(self):
        if sys.platform!='win32':self.publish(Track(),[],'windows_only');return
        try:
            from winrt.runtime import init_apartment,uninit_apartment,ApartmentType
            init_apartment(ApartmentType.MULTI_THREADED)
            try:asyncio.run(self.poll())
            finally:uninit_apartment()
        except Exception:self.publish(Track(),[],'media_unavailable')
        finally:self.netease.close()
    async def poll(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        manager=await Manager.request_async();previous='';covers=CoverCache()
        while not self.stop.is_set():
            try:
                items=[]
                for session in manager.get_sessions():
                    try:items.append((session.source_app_user_model_id,int(session.get_playback_info().playback_status)==4,session))
                    except Exception:continue
                preference=self.preference()
                native_netease = has_native_netease(items)
                if not native_netease:
                    try:
                        track=self.netease.observe(timing=not preference or preference==NETEASE_FALLBACK)
                        items=append_fallback(items,track)
                    except Exception:pass  # Optional fallback must not break SMTC.
                chosen=choose_session(items,preference,previous)
                selected_netease = native_netease and chosen is not None and identify_player(chosen[0]) == 'netease'
                if native_netease and not selected_netease:
                    self.netease.close()
                sources=[dict(id=x[0],label=x[0]) for x in items]
                if chosen is None:self.publish(Track(),sources,'no_session');previous=''
                elif chosen[0]==NETEASE_FALLBACK:
                    track=chosen[2]
                    artwork=await covers.get(track.key,track.cover_url or None,time.monotonic())
                    self.publish(replace(track,cover=artwork),sources,'ready' if track.position is not None else 'audio_only')
                    previous=chosen[0]
                else:
                    app,playing,session=chosen;props=await asyncio.wait_for(session.try_get_media_properties_async(),2)
                    duration, position = read_timeline(session, playing, allow_partial=selected_netease)
                    track = Track(
                        source=app, title=(props.title or '')[:512], artist=(props.artist or '')[:512],
                        album=(props.album_title or '')[:512], duration=duration, position=position,
                        playing=playing, observed=time.monotonic(),
                    )
                    if selected_netease:
                        track = self.netease.fill_native_timeline(track)
                    reference=props.thumbnail
                    if reference is None and selected_netease and track.title and track.artist:
                        record=self.netease.queue.find(track.title,track.artist)
                        if record:
                            reference=record.cover_url or None
                    cover=await covers.get(track.key,reference,time.monotonic())
                    if not self.stop.is_set():self.publish(replace(track, cover=cover),sources,'ready')
                    previous=app
            except Exception:self.publish(Track(),[],'media_unavailable')
            for _ in range(5):
                if self.stop.is_set():break
                await asyncio.sleep(.1)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(3)
        return not self.thread or not self.thread.is_alive()

class Loopback:
    def __init__(self,publish):self.publish=publish;self.stop=threading.Event();self.thread=None
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True,name='RIO-audio');self.thread.start()
    def run(self):
        if sys.platform!='win32':self.publish(Audio(status='windows_only'));return
        try:
            import pyaudiowpatch as pa
            import numpy as np
        except ImportError:self.publish(Audio(status='dependency_missing'));return
        while not self.stop.is_set():
            try:
                with pa.PyAudio() as audio:
                    device=audio.get_default_wasapi_loopback();channels=int(device['maxInputChannels']);rate=int(device['defaultSampleRate']);spectrum=Spectrum(rate)
                    def callback(data,count,info,status):
                        if self.stop.is_set():return (None,pa.paComplete)
                        try:self.publish(spectrum.analyze(np.frombuffer(data,dtype=np.float32),channels,time.monotonic()))
                        except Exception:self.publish(Audio(status='audio_error'))
                        return (None,pa.paContinue)
                    stream=audio.open(format=pa.paFloat32,channels=channels,rate=rate,input=True,input_device_index=device['index'],frames_per_buffer=2048,stream_callback=callback)
                    try:
                        self.publish(Audio(status='ready'))
                        while not self.stop.wait(1) and stream.is_active():
                            # Reopen after changing default speakers/headphones.
                            current=audio.get_default_wasapi_loopback()
                            if current['index']!=device['index']:break
                    finally:stream.close()
            except Exception:self.publish(Audio(status='audio_unavailable'))
            self.stop.wait(1)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
        return not self.thread or not self.thread.is_alive()
