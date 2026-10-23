import io, struct, tempfile, threading, unittest, subprocess
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from rio_monitor.resources import (ResourceSender,resource_cdb,pack_resource,
                                  RESOURCE_WINDOW,BLOCK,QUERY,PLAY,MAX_MEDIA_BYTES,QUERY_SETTLE_SECONDS)
from rio_monitor.protocol import ProtocolError
from rio_monitor.storage import DisplaySession,StorageJob
from rio_monitor.media import prepare_media

def gif():
    f=io.BytesIO();Image.new('RGB',(480,480),'#ffcc00').save(f,'GIF');return f.getvalue()

class Transport:
    def __init__(self):
        self.commands=[];self.payloads=[];self.tag=0;self.length=0;self.fail=None;self.dimensions=(480,480);self.revision=0x0200
    def device_descriptor(self):
        d=bytearray(18);d[:2]=b'\x12\x01';struct.pack_into('<HHH',d,8,0x2a55,0x9990,self.revision);return bytes(d)
    def write(self,ep,data):
        assert ep==1
        if len(data)==31 and data[:4]==b'USBC':
            _,self.tag,self.length,direction,_,_,cdb=struct.unpack('<4sIIBBB16s',data)
            self.commands.append(cdb)
            if cdb==QUERY:assert direction==0x80
        else:self.payloads.append(data)
        return len(data)-(1 if self.fail=='short_write' and len(self.commands)>1 else 0)
    def read(self,ep,count):
        assert ep==0x81
        if count==5:return struct.pack('<HHB',*self.dimensions,255)
        tag=self.tag+1 if self.fail=='tag' else self.tag
        residue=1 if self.fail=='residue' else self.length
        return struct.pack('<4sIIB',b'USBS',tag,residue,1 if self.fail=='status' else 0)
    def close(self):pass
    def set_timeout(self,value):pass

class ResourceTests(unittest.TestCase):
    def test_query_settles_before_cache_invalidation_and_first_erase(self):
        transport=Transport();settled=[];write=transport.write
        def guarded_write(ep,data):
            if len(data)==31 and data[15:17]==b'\xfb\xd8':
                self.assertEqual(settled,['settled','invalidated'])
            return write(ep,data)
        transport.write=guarded_write
        def settle(seconds):
            self.assertEqual(seconds,QUERY_SETTLE_SECONDS);self.assertGreaterEqual(seconds,1.0)
            self.assertEqual(transport.commands,[QUERY]);settled.append('settled')
        with patch('rio_monitor.resources.time.sleep',side_effect=settle) as wait:
            ResourceSender(transport).upload(pack_resource(gif()),before_erase=lambda:settled.append('invalidated'))
        wait.assert_called_once();self.assertEqual(transport.commands[-1],PLAY)
    def test_failed_query_does_not_wait_invalidate_or_erase(self):
        transport=Transport();transport.fail='status';invalidate=Mock()
        with patch('rio_monitor.resources.time.sleep') as wait:
            with self.assertRaises(ProtocolError):
                ResourceSender(transport).upload(pack_resource(gif()),before_erase=invalidate)
        wait.assert_not_called();invalidate.assert_not_called();self.assertEqual(transport.commands,[QUERY])
    def test_roundtrip_blocks_and_play_after_last_ack(self):
        transport=Transport();sender=ResourceSender(transport);blob=pack_resource(gif());events=[]
        sender.upload(blob,lambda *v:events.append(v))
        self.assertEqual(transport.commands[0],QUERY);self.assertEqual(transport.commands[-1],PLAY)
        self.assertEqual(b''.join(transport.payloads),blob)
        erases=[c for c in transport.commands if c[:2]==b'\xfb\xd8'];writes=[c for c in transport.commands if c[:2]==b'\xfb\xd9']
        self.assertEqual(len(erases),(len(blob)+BLOCK-1)//BLOCK);self.assertEqual(len(erases),len(writes))
        self.assertTrue(all(c[:2]==b'\xfb\xd8' for c in transport.commands[1:1+len(erases)]))
        self.assertEqual(events[-1],('stored',len(erases)*2+1,len(erases)*2+1))
        self.assertTrue(all(done<total for _,done,total in events[:-1]))
    def test_invalid_payload_and_target_do_not_erase(self):
        for blob in (b'',b'\x02'+bytes(20),pack_resource(gif())[:-1]):
            t=Transport()
            with self.assertRaises(ValueError):ResourceSender(t).upload(blob)
            self.assertFalse(t.commands)
        for dimensions,revision in (((800,480),0x200),((480,480),0x201)):
            t=Transport();t.dimensions=dimensions;t.revision=revision
            with self.assertRaises(ProtocolError):ResourceSender(t).upload(pack_resource(gif()))
            self.assertFalse(any(c[:1]==b'\xfb' for c in t.commands))
    def test_flash_bounds_and_command_allowlist(self):
        for op,offset,length in (('firmware',0,0),('erase',-BLOCK,0),('erase',1,0),('erase',RESOURCE_WINDOW,0),('write',0,0),('write',0,BLOCK+1),('write',RESOURCE_WINDOW,1)):
            with self.assertRaises(ValueError):resource_cdb(op,offset,length)
        self.assertEqual(len(resource_cdb('erase',RESOURCE_WINDOW-BLOCK)),16)
        t=Transport();s=ResourceSender(t)
        for cdb in (bytes.fromhex('fbda')+bytes(14),bytes(16),QUERY[:-1]+b'\x01'):
            with self.assertRaises(ValueError):s.exchange(cdb)
        self.assertFalse(t.commands)
    def test_transport_fault_stops_without_retry_or_play(self):
        for fault in ('tag','residue','status','short_write'):
            t=Transport();t.fail=fault;s=ResourceSender(t)
            with self.assertRaises(ProtocolError):s.upload(pack_resource(gif()))
            count=len(t.commands)
            with self.assertRaises(ProtocolError):s.exchange(PLAY)
            self.assertEqual(len(t.commands),count);self.assertNotIn(PLAY,t.commands)

class OwnershipTests(unittest.TestCase):
    def test_frame_owner_is_closed_before_resource_handle_opens(self):
        order=[];output=Mock(error=None,sent=2)
        output.close.side_effect=lambda:order.append('closed') or True
        t=Transport()
        def transport_factory(path):self.assertEqual(order,['closed']);order.append('resource');return t
        s=DisplaySession(enumerator=lambda:['device'],transport_factory=transport_factory);s.output=output
        s.replace(pack_resource(gif()),lambda *args:None);s.submit(Image.new('RGB',(480,480)))
        self.assertEqual(s.mode,'stored');output.submit.assert_not_called();self.assertFalse(s.resource_active)
    def test_old_writer_refusing_shutdown_prevents_all_resource_commands(self):
        factory=Mock();s=DisplaySession(enumerator=lambda:['device'],transport_factory=factory)
        s.output=Mock();s.output.close.return_value=False
        with self.assertRaises(RuntimeError):s.replace(pack_resource(gif()),lambda *args:None)
        factory.assert_not_called();self.assertFalse(s.resource_active);self.assertEqual(s.mode,'stored')
    def test_multiple_devices_do_not_open_resource_handle(self):
        factory=Mock();s=DisplaySession(enumerator=lambda:['one','two'],transport_factory=factory)
        with self.assertRaises(RuntimeError):s.replace(pack_resource(gif()),lambda *args:None)
        factory.assert_not_called()
    def test_preview_never_opens_usb_and_shutdown_waits_for_writer(self):
        s=Mock(mode='monitor');job=StorageJob(s,Path())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'art.png';Image.new('RGB',(32,64),'red').save(p)
            job.prepare(p);job.thread.join(5)
            self.assertTrue(job.snapshot()['ready']);s.replace.assert_not_called();s.connect.assert_not_called()
            active=threading.Event();finish=threading.Event()
            def replace(*args):active.set();finish.wait(5)
            s.replace.side_effect=replace;self.assertTrue(job.write());self.assertTrue(active.wait(2))
            self.assertFalse(job.close());self.assertFalse(job.write());self.assertFalse(job.prepare(p))
            finish.set();job.thread.join(5);self.assertTrue(job.close())

class MediaTests(unittest.TestCase):
    def test_static_image_is_contained_and_preview_matches_resource(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'image.png';Image.new('RGBA',(120,60),(255,0,0,255)).save(p)
            prepared=prepare_media(p,Path(td)/'job',Path('missing-ffmpeg.exe'))
            self.assertEqual(prepared.frames,1);self.assertEqual(prepared.gif,prepared.preview.read_bytes())
            with Image.open(prepared.preview) as im:
                im=im.convert('RGB');self.assertEqual(im.size,(480,480));self.assertEqual(im.getpixel((240,0)),(0,0,0));self.assertEqual(im.getpixel((240,240)),(255,0,0))
    def test_native_gif_remains_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'image.gif';raw=gif();p.write_bytes(raw)
            prepared=prepare_media(p,Path(td)/'job',Path('missing-ffmpeg.exe'))
            self.assertEqual(prepared.gif,raw)
    def test_animated_webp_keeps_frames_and_timing(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'animation.webp'
            Image.new('RGB',(64,64),'red').save(p,'WEBP',save_all=True,append_images=[Image.new('RGB',(64,64),'blue')],duration=[100,200],lossless=True,loop=0)
            prepared=prepare_media(p,Path(td)/'job',Path('missing-ffmpeg.exe'))
            self.assertEqual(prepared.frames,2);self.assertEqual(prepared.duration_ms,300)
            with Image.open(prepared.preview) as im:
                im.seek(0);self.assertEqual(im.convert('RGB').getpixel((240,240)),(255,0,0))
                im.seek(1);self.assertEqual(im.convert('RGB').getpixel((240,240)),(0,0,255))
    def test_video_conversion_produces_complete_30fps_gif(self):
        ffmpeg=Path(__file__).resolve().parents[1]/'assets/media/ffmpeg.exe'
        if not ffmpeg.is_file():self.skipTest('Private bundled video converter unavailable')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'clip.mp4'
            subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=96x64:rate=30','-t','0.5','-c:v','libx264','-pix_fmt','yuv420p',str(p)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            prepared=prepare_media(p,Path(td)/'job',ffmpeg)
            self.assertEqual(prepared.frames,15);self.assertEqual(prepared.duration_ms,500)
            self.assertLessEqual(len(prepared.gif),MAX_MEDIA_BYTES);self.assertTrue(prepared.gif.endswith(b';'))
    def test_oversized_source_fails_before_converter_or_usb(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'image.mp4';p.write_bytes(bytes(MAX_MEDIA_BYTES+1))
            with patch('rio_monitor.media.convert_animation') as convert:
                with self.assertRaises(ValueError):prepare_media(p,Path(td)/'job',Path())
                convert.assert_not_called()
    def test_converted_video_over_limit_is_rejected_instead_of_truncated(self):
        ffmpeg=Path(__file__).resolve().parents[1]/'assets/media/ffmpeg.exe'
        if not ffmpeg.is_file():self.skipTest('Private bundled video converter unavailable')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'clip.mp4'
            subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=96x64:rate=30','-t','3','-c:v','libx264','-pix_fmt','yuv420p',str(p)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertLess(p.stat().st_size,MAX_MEDIA_BYTES)
            with self.assertRaisesRegex(ValueError,'3.4 MB'):prepare_media(p,Path(td)/'job',ffmpeg)

class DefaultTests(unittest.TestCase):
    def test_private_default_restores_only_after_explicit_action(self):
        assets=Path(__file__).resolve().parents[1]/'assets'
        default=assets/'default-screen.gif'
        if not default.is_file():self.skipTest('Private default animation unavailable')
        session=Mock(mode='monitor');called=threading.Event()
        session.replace.side_effect=lambda blob,progress:called.set()
        job=StorageJob(session,assets)
        session.replace.assert_not_called()
        self.assertTrue(job.prepare(default,write_after=True));self.assertTrue(called.wait(5))
        job.thread.join(5);self.assertTrue(job.close());session.replace.assert_called_once()
        self.assertEqual(session.replace.call_args.args[0],pack_resource(default.read_bytes()))
