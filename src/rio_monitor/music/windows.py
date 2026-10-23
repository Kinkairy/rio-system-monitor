"""Windows-only providers. Lazy imports keep monitor mode independent."""
import asyncio,datetime,time,threading,sys
from .state import Track,Audio,Spectrum,select_session

async def read_cover(reference):
    if reference is None:return b''
    from winrt.windows.storage.streams import DataReader
    stream=await reference.open_read_async()
    try:
        if stream.size>4*1024*1024:return b''
        reader=DataReader(stream)
        try:
            count=await reader.load_async(int(stream.size));data=bytearray(count)
            reader.read_bytes(data)
            return bytes(data)
        finally:reader.close()
    finally:stream.close()

class CoverCache:
    """Retry late thumbnails without discarding a good cover for the same track."""
    def __init__(self):self.key=None;self.data=b'';self.retry_at=0
    async def get(self,key,reference,now):
        if key!=self.key:self.key=key;self.data=b'';self.retry_at=0
        if not self.data and now>=self.retry_at:
            self.retry_at=now+2
            try:self.data=await asyncio.wait_for(read_cover(reference),2)
            except Exception:pass
        return self.data

class MediaSessions:
    def __init__(self,publish,preference):self.publish=publish;self.preference=preference;self.stop=threading.Event();self.thread=None
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
    async def poll(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        manager=await Manager.request_async();previous='';covers=CoverCache()
        while not self.stop.is_set():
            try:
                items=[]
                for session in manager.get_sessions():
                    try:items.append((session.source_app_user_model_id,int(session.get_playback_info().playback_status)==4,session))
                    except Exception:continue
                chosen=select_session(items,self.preference(),previous)
                sources=[dict(id=x[0],label=x[0]) for x in items]
                if chosen is None:self.publish(Track(),sources,'no_session');previous=''
                else:
                    app,playing,session=chosen;props=await asyncio.wait_for(session.try_get_media_properties_async(),2)
                    timeline=session.get_timeline_properties();position=None;duration=0
                    try:
                        duration=max(0,(timeline.end_time-timeline.start_time).total_seconds())
                        if duration>0:
                            position=max(0,(timeline.position-timeline.start_time).total_seconds())
                            # Honor the provider's update anchor; don't restart elapsed time each poll.
                            if playing:
                                stamp=timeline.last_updated_time
                                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=datetime.timezone.utc)
                                delta=(datetime.datetime.now(datetime.timezone.utc)-stamp).total_seconds()
                                if 0<=delta<=5:position=min(duration,position+delta)
                    except Exception:pass
                    key=(app,props.title,props.artist,props.album_title)
                    cover=await covers.get(key,props.thumbnail,time.monotonic())
                    track=Track(app,(props.title or '')[:512],(props.artist or '')[:512],(props.album_title or '')[:512],duration,position,playing,time.monotonic(),cover)
                    if not self.stop.is_set():self.publish(track,sources,'ready')
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
