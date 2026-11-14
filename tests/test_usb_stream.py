"""Regression model keeps the device's incoming FIFO across host handles."""
from collections import deque
import struct
import unittest
from unittest.mock import patch
from rio_monitor import protocol


def csw(tag, length=460800, status=0):
    return struct.pack('<4sIIB', b'USBS', tag, length, status)


class Device:
    def __init__(self):
        self.incoming=deque(); self.writes=[]; self.reads=0; self.tag=0
        self.length=0; self.fragment=512; self.delay=None; self.geometry=(480,480)
        self.reject=0; self.fail_write=None
    def open(self):
        return Handle(self)
    def respond(self, data):
        if self.delay:
            self.incoming.append(self.delay); self.delay=None
        self.incoming.append(data)


class Handle:
    def __init__(self, device): self.device=device; self.closed=False
    def close(self): self.closed=True
    def write(self, ep, data):
        d=self.device; d.writes.append(data)
        if d.fail_write: raise d.fail_write
        if len(data)==31 and data[:4]==b'USBC':
            _,d.tag,d.length,_,_,_,cdb=struct.unpack('<4sIIBBB16s',data)
            if cdb[5]==3:
                d.respond(struct.pack('<HHB',*d.geometry,255))
                d.incoming.append(csw(d.tag,5,d.reject))
        else: d.respond(csw(d.tag,d.length,d.reject))
        return len(data)
    def read(self, ep, length):
        d=self.device; d.reads+=1
        if not d.incoming: raise OSError(121,'no reply yet')
        value=d.incoming.popleft()
        if isinstance(value,Exception): raise value
        amount=min(length,d.fragment,len(value))
        if amount<len(value):d.incoming.appendleft(value[amount:])
        return value[:amount]


class USBStreamTests(unittest.TestCase):
    def test_fragmented_query_and_frame_status_are_reassembled(self):
        for fragment in (1,2,3,4,7,12):
            with self.subTest(fragment=fragment):
                d=Device();d.fragment=fragment;s=protocol.FrameSender(d.open())
                self.assertEqual(s.lcd_info(),(480,480,255))
                s.send(bytes(460800));self.assertFalse(s.faulted)
                self.assertEqual(len(d.writes),3)

    def test_one_read_timeout_waits_for_same_transaction_without_rewriting(self):
        for query in (True,False):
            with self.subTest(query=query):
                d=Device();d.delay=OSError(121,'delayed reply');s=protocol.FrameSender(d.open())
                if query:self.assertEqual(s.lcd_info(),(480,480,255))
                else:s.send(bytes(460800))
                self.assertEqual(len(d.writes),1 if query else 2)
                self.assertFalse(s.faulted)

    def test_zero_length_packet_is_not_a_complete_status(self):
        d=Device();d.incoming.append(b'');s=protocol.FrameSender(d.open())
        s.send(bytes(460800));self.assertFalse(s.faulted)

    def test_late_csw_survives_reopen_and_is_not_lcd_dimensions(self):
        d=Device();old=d.open();first=protocol.FrameSender(old)
        first.send(bytes(460800));old_tag=first.tag;old.close()
        d.incoming.extend((csw(old_tag),))
        newer=protocol.FrameSender(d.open())
        self.assertEqual(newer.lcd_info(),(480,480,255))
        self.assertNotEqual(newer.tag,old_tag)
        newer.send(bytes(460800));self.assertFalse(newer.faulted)

    def test_old_geometry_and_status_cannot_satisfy_new_query(self):
        d=Device();first=protocol.FrameSender(d.open());first.lcd_info()
        d.incoming.extend((struct.pack('<HHB',320,240,0),csw(first.tag,5)))
        self.assertEqual(protocol.FrameSender(d.open()).lcd_info(),(480,480,255))

    def test_old_success_cannot_hide_current_device_rejection(self):
        d=Device();first=protocol.FrameSender(d.open());first.send(bytes(460800))
        d.incoming.append(csw(first.tag));d.reject=1
        with self.assertRaisesRegex(protocol.ProtocolError,'Device rejected'):
            protocol.FrameSender(d.open()).send(bytes(460800))

    def test_partial_old_status_tail_is_discarded_before_current_query_pair(self):
        d=Device();d.incoming.append(csw(17)[5:])
        self.assertEqual(protocol.FrameSender(d.open()).lcd_info(),(480,480,255))

    def test_timeout_after_status_fragment_keeps_received_bytes(self):
        d=Device();s=protocol.FrameSender(d.open());original=d.respond
        def split(data):
            d.incoming.extend((data[:6],OSError(121,'late tail'),data[6:]))
        d.respond=split
        s.send(bytes(460800));self.assertFalse(s.faulted)
        self.assertEqual(len(d.writes),2)

    def test_current_bad_geometry_consumes_status_but_never_sends_frame(self):
        d=Device();d.geometry=(320,240);s=protocol.FrameSender(d.open())
        with self.assertRaisesRegex(protocol.ProtocolError,'Unsupported display size'):s.lcd_info()
        self.assertFalse(d.incoming)
        with self.assertRaises(protocol.ProtocolError):s.send(bytes(460800))
        self.assertEqual(len(d.writes),1)

    def test_endless_timeout_and_garbage_are_bounded(self):
        for values in ((OSError(121,'missing'),)*100,(b'x'*13,)*100,(b'',)*100):
            d=Device();d.incoming.extend(values);s=protocol.FrameSender(d.open())
            with self.assertRaises(protocol.ProtocolError):s.send(bytes(460800))
            self.assertLessEqual(d.reads,64);self.assertEqual(len(d.writes),2)
            self.assertTrue(s.faulted)

    def test_out_failure_is_never_retried_or_counted_as_success(self):
        d=Device();d.fail_write=OSError(121,'uncertain write');d.fail_write.usb_reported=359936
        s=protocol.FrameSender(d.open())
        with self.assertRaises(protocol.ProtocolError):s.send(bytes(460800))
        self.assertEqual(len(d.writes),1);self.assertEqual(d.reads,0)

    def test_non_timeout_read_error_is_not_retried(self):
        d=Device();d.delay=OSError(5,'access denied');s=protocol.FrameSender(d.open())
        with self.assertRaises(protocol.ProtocolError):s.send(bytes(460800))
        self.assertEqual(d.reads,1)

    def test_reported_partial_failed_read_is_not_used_as_valid_bytes(self):
        d=Device();error=OSError(121,'partial failed');error.usb_reported=7;d.delay=error
        s=protocol.FrameSender(d.open())
        with self.assertRaises(protocol.ProtocolError):s.send(bytes(460800))
        self.assertEqual(d.reads,1)
