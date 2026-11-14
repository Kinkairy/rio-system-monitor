"""Complete bounded frames remain invisible until validated END; no USB."""
import ctypes,random,unittest
import test_lt168b_stream as receiver
from rio_monitor.lt168b_stream import encode_frame,packet,FRAME_BYTES

SYNC=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)
class PresentationTests(receiver.ReceiverTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lib.rio_stream_staging.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,SYNC,ctypes.c_void_p]
        for name in ('rio_stream_presentations','rio_stream_fallbacks'):
            f=getattr(cls.lib,name);f.argtypes=[ctypes.c_void_p];f.restype=ctypes.c_uint32
    def setUp(self):
        super().setUp()
        self.arena=ctypes.create_string_buffer(b'\x9b'*(208*1024+32),208*1024+32)
        self.row=ctypes.create_string_buffer(b'\x6d'*(15360+32),15360+32)
        self.sync_allowed=True;self.sync_calls=0
        def sync(context):self.sync_calls+=1;return int(self.sync_allowed)
        self.sync=SYNC(sync);self.bind()
    def bind(self):
        self.lib.rio_stream_staging(self.state,ctypes.addressof(self.arena)+16,208*1024,ctypes.addressof(self.row)+16,self.sync,None)
    def tearDown(self):
        super().tearDown()
        self.assertEqual(self.arena.raw[:16]+self.arena.raw[-16:],b'\x9b'*32)
        self.assertEqual(self.row.raw[:16]+self.row.raw[-16:],b'\x6d'*32)
    def parts(self,frame,seq=1,base=None):
        return list(encode_frame(frame,session=133,frame=seq,acknowledged=base,compression=True))
    def test_no_visible_tile_before_end_and_exact_after_end(self):
        old=bytes([0x07,0xe0])*(FRAME_BYTES//2)
        new=bytes([0xf8,0])*(FRAME_BYTES//2)
        for seq,frame,base in ((1,old,None),(2,new,old)):
            before=self.storage.raw;parts=self.parts(frame,seq,base)
            self.assertEqual(self.feed(b''.join(parts[:-1])),0)
            self.assertEqual(self.storage.raw,before)
            self.assertEqual(self.feed(parts[-1],1),1);self.expect_pixels(frame)
        self.assertEqual(self.sync_calls,2)
        self.assertEqual(self.lib.rio_stream_presentations(self.state),2)
        self.assertEqual(self.lib.rio_stream_fallbacks(self.state),0)
    def test_bad_late_crc_and_incomplete_frame_keep_previous_image(self):
        old=bytes([0x12,0x34])*(FRAME_BYTES//2);new=bytes(FRAME_BYTES)
        self.assertEqual(self.feed(b''.join(self.parts(old))),1)
        before=self.storage.raw;parts=self.parts(new,2,old)
        self.assertEqual(self.feed(b''.join(parts[:100])),0)
        bad=bytearray(parts[100]);bad[-1]^=1
        self.assertEqual(self.feed(bytes(bad)),-1)
        self.assertEqual(self.storage.raw,before);self.assertEqual(self.sync_calls,1)
        self.lib.rio_stream_init(self.state,ctypes.addressof(self.storage)+16);self.bind()
        self.assertEqual(self.feed(b''.join(self.parts(new)[:-1])),0)
        self.assertEqual(self.storage.raw,before)
    def test_missing_tile_end_keeps_old_picture(self):
        parts=self.parts(bytes(FRAME_BYTES));before=self.storage.raw
        self.assertEqual(self.feed(b''.join(parts[:100]+parts[101:])),-1)
        self.assertEqual(self.storage.raw,before);self.assertEqual(self.sync_calls,0)
    def test_sync_timeout_rejects_before_mutation_and_can_reset(self):
        self.sync_allowed=False;before=self.storage.raw;frame=bytes(FRAME_BYTES)
        self.assertEqual(self.feed(b''.join(self.parts(frame))),-1)
        self.assertEqual(self.storage.raw,before);self.assertEqual(self.lib.rio_stream_completed(self.state),0)
        self.sync_allowed=True
        self.assertEqual(self.feed(b''.join(self.parts(frame,2))),1);self.expect_pixels(frame)
    def test_shuffled_tiles_present_in_bands_without_changing_pixels(self):
        frame=bytes((i//64)%256 for i in range(FRAME_BYTES));parts=self.parts(frame)
        self.assertEqual(self.feed(parts[0]+b''.join(reversed(parts[1:-1]))),0)
        self.assertEqual(self.storage.raw,b'\xa7'*(FRAME_BYTES+32))
        self.assertEqual(self.feed(parts[-1]),1);self.expect_pixels(frame)
        self.assertEqual(self.lib.rio_stream_fallbacks(self.state),0)
    def test_oversize_preserves_original_lossless_progressive_support(self):
        frame=random.Random(912).randbytes(FRAME_BYTES)
        self.assertEqual(self.feed(b''.join(self.parts(frame))),1);self.expect_pixels(frame)
        self.assertEqual(self.lib.rio_stream_fallbacks(self.state),1)
        # Return to staged mode on the next small delta.
        new=bytearray(frame);new[-2:]=b'\x00\x00';before=self.storage.raw
        parts=self.parts(bytes(new),2,frame)
        self.assertEqual(self.feed(b''.join(parts[:-1])),0);self.assertEqual(self.storage.raw,before)
        self.assertEqual(self.feed(parts[-1]),1);self.expect_pixels(bytes(new))

    def test_compressed_overflow_restores_current_decoder_scratch(self):
        # Deliberately tiny arena: overflow inside compressed tiles after
        # present() has reused decoder scratch for a different preceding tile.
        self.lib.rio_stream_staging(self.state,ctypes.addressof(self.arena)+16,100,
            ctypes.addressof(self.row)+16,self.sync,None)
        old=bytes((i//64)%256 for i in range(FRAME_BYTES))
        new=bytes((255-i//64)%256 for i in range(FRAME_BYTES))
        for seq,frame,base in ((1,old,None),(2,new,old)):
            parts=self.parts(frame,seq,base)
            self.assertTrue(all(p[5]==5 for p in parts[1:-1]))
            self.assertEqual(self.feed(b''.join(parts),7),1);self.expect_pixels(frame)
        self.assertEqual(self.lib.rio_stream_fallbacks(self.state),2)
    def test_unchanged_delta_does_not_wait_or_present(self):
        frame=bytes(FRAME_BYTES)
        self.assertEqual(self.feed(b''.join(self.parts(frame))),1)
        self.sync_allowed=False
        self.assertEqual(self.feed(b''.join(self.parts(frame,2,frame))),1)
        self.assertEqual(self.sync_calls,1);self.expect_pixels(frame)

    def test_after_present_observes_final_pixels_and_not_rejected_or_empty_frames(self):
        callback_type=ctypes.CFUNCTYPE(None,ctypes.c_void_p)
        self.lib.rio_stream_on_presented.argtypes=[ctypes.c_void_p,callback_type]
        observations=[]
        callback=callback_type(lambda context:observations.append(self.storage.raw[16:-16]))
        self.lib.rio_stream_on_presented(self.state,callback)
        frame=bytes(FRAME_BYTES);parts=self.parts(frame)
        self.assertEqual(self.feed(b''.join(parts[:-1])),0);self.assertEqual(observations,[])
        self.assertEqual(self.feed(parts[-1]),1);self.assertEqual(observations,[frame])
        self.assertEqual(self.feed(b''.join(self.parts(frame,2,frame))),1)
        self.sync_allowed=False
        self.assertEqual(self.feed(b''.join(self.parts(bytes([255])*FRAME_BYTES,3,frame))),-1)
        self.assertEqual(observations,[frame])

if __name__=='__main__':unittest.main()
