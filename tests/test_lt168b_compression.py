"""Bounded lossless decoder vs independent RGB565 oracle; no device access."""
import random
import unittest
from lz4.block import compress
import test_lt168b_stream as receiver
from rio_monitor.lt168b_stream import encode_frame, packet, FRAME_BYTES, HEADER, COMPRESSED_TILE

class CompressionTests(receiver.ReceiverTests):
    def test_compressed_absolute_predictor_and_incompressible_exact(self):
        rng=random.Random(811)
        frames=[bytes(FRAME_BYTES), bytes([31,84])*(FRAME_BYTES//2),
                rng.randbytes(FRAME_BYTES)]
        change=bytearray(frames[-1])
        for at in range(0,FRAME_BYTES,109):change[at]^=1
        frames.append(bytes(change));previous=None;operations=set();predictors=set()
        for seq,frame in enumerate(frames,1):
            parts=list(encode_frame(frame,session=133,frame=seq,acknowledged=previous,compression=True))
            for p in parts:
                kind=HEADER.unpack(p[:20])[2];operations.add(kind)
                if kind==COMPRESSED_TILE:predictors.add(p[24])
            self.assertEqual(self.feed(b''.join(parts),4093),1)
            self.expect_pixels(frame);previous=frame
        self.assertTrue({3,5} <= operations)
        self.assertEqual(predictors,{0,1})

    def test_malformed_compression_never_writes_tile(self):
        bad=[b'', b'\0', b'\2'+compress(bytes(1024),store_size=False),
             b'\1'+compress(bytes(1024),store_size=False),
             b'\0'+compress(bytes(1023),store_size=False),
             b'\0'+compress(bytes(1025),store_size=False),
             b'\0\xff'+b'\xff'*500,
             b'\0\x00\x00\x00',
             b'\0'+compress(bytes(1024),store_size=False)[:-1]]
        for payload in bad:
            with self.subTest(payload=payload[:8]):
                self.setUp();self.feed(packet(1,133,1,450))
                self.assertEqual(self.feed(packet(5,133,1,0,payload),1),-1)
                self.assertEqual(self.storage.raw,b'\xa7'*(FRAME_BYTES+32))
                self.assertEqual(self.lib.rio_stream_completed(self.state),0)

    def test_duplicate_predictor_rejected_before_second_xor(self):
        base=bytes(FRAME_BYTES);self.assertEqual(self.send(base),1)
        self.feed(packet(2,133,2,1))
        p=packet(5,133,2,0,b'\1'+compress(bytes([3])*1024,store_size=False))
        self.assertEqual(self.feed(p),0);snapshot=self.storage.raw
        self.assertEqual(self.feed(p),-1);self.assertEqual(self.storage.raw,snapshot)

    def test_corrupt_compressed_crc_does_not_decode(self):
        self.feed(packet(1,133,1,450))
        p=bytearray(packet(5,133,1,0,b'\0'+compress(bytes(1024),store_size=False)));p[-1]^=1
        self.assertEqual(self.feed(bytes(p)),-1)
        self.assertEqual(self.storage.raw,b'\xa7'*(FRAME_BYTES+32))

if __name__=='__main__':unittest.main()
