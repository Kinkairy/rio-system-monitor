import random
import struct
import unittest
from unittest.mock import patch
from PIL import Image
from rio_monitor.protocol import encode_rgb565,frame_command,FrameSender,ProtocolError,validate_status
from rio_monitor.winusb import interface_guids


class Transport:
    def __init__(self,geometry=(480,480),residue=True,status=0):
        self.geometry=geometry;self.residue=residue;self.status=status;self.writes=[];self.info_pending=False
    def write(self,ep,data):
        assert ep==1
        self.writes.append(data)
        if len(data)==31 and data.startswith(b'USBC'):
            _,self.tag,self.length,_,_,_,cdb=struct.unpack('<4sIIBBB16s',data)
            self.info_pending=cdb[5]==3
        return len(data)
    def read(self,ep,length):
        assert ep==0x81
        if self.info_pending:
            self.info_pending=False
            return struct.pack('<HHB',*self.geometry,255)
        return struct.pack('<4sIIB',b'USBS',self.tag,self.length if self.residue else 0,self.status)


class USBCompatibilityTests(unittest.TestCase):
    def test_rgb565_matches_reference(self):
        rng=random.Random(42)
        colors=[(255,0,0),(0,255,0),(0,0,255),(255,255,255),(0,0,0)]+[tuple(rng.randrange(256) for _ in range(3)) for _ in range(256)]
        image=Image.new('RGB',(len(colors),1));image.putdata(colors)
        expected=b''.join(struct.pack('>H',((r & 0xf8)<<8)|((g & 0xfc)<<3)|(b>>3)) for r,g,b in colors)
        self.assertEqual(encode_rgb565(image),expected)

    def test_incomplete_frames_are_rejected_before_usb(self):
        for payload in (b'',b'\xff\xd8\xff\xd9',bytes(480*480*2-1)):
            with self.assertRaises(ValueError):frame_command(payload,1)
        self.assertEqual(struct.unpack_from('<I',frame_command(bytes(460800),1),8)[0],460800)

    def test_query_and_frames_accept_exact_firmware_residue(self):
        for residue in (True,False):
            transport=Transport(residue=residue);sender=FrameSender(transport)
            self.assertEqual(sender.lcd_info(),(480,480,255))
            for _ in range(3):sender.send(bytes(460800))
            self.assertEqual(sender.tag,4)
            self.assertFalse(sender.faulted)
            self.assertEqual([len(data) for data in transport.writes],[31,31,460800,31,460800,31,460800])

    def test_arbitrary_residue_is_rejected(self):
        for residue in (1,460799,460801):
            with self.assertRaises(ProtocolError):
                validate_status(struct.pack('<4sIIB',b'USBS',7,residue,0),7,460800)

    def test_rejected_status_latches_and_prevents_retry(self):
        transport=Transport(status=1);sender=FrameSender(transport)
        with self.assertRaises(ProtocolError):sender.send(bytes(460800))
        self.assertTrue(sender.faulted);count=len(transport.writes)
        with self.assertRaises(ProtocolError):sender.send(bytes(460800))
        self.assertEqual(len(transport.writes),count)

    def test_other_geometry_stops_before_any_frame(self):
        transport=Transport(geometry=(320,240));sender=FrameSender(transport)
        with self.assertRaises(ProtocolError):sender.lcd_info()
        with self.assertRaises(ProtocolError):sender.send(bytes(460800))
        self.assertEqual(len(transport.writes),1)

    def test_short_lcd_reply_stops(self):
        transport=Transport();sender=FrameSender(transport)
        with patch.object(transport,'read',return_value=b'\x00'):
            with self.assertRaises(ProtocolError):sender.lcd_info()
        self.assertTrue(sender.faulted)

    def test_both_windows_registry_value_names(self):
        cases=[{'DeviceInterfaceGUID':'{single}'},{'DeviceInterfaceGUIDs':['{a}','{b}']},{'DeviceInterfaceGUIDs':['{a}'],'DeviceInterfaceGUID':'{a}'},{}]
        for values in cases:
            def query(key,name):
                if name not in values:raise FileNotFoundError(name)
                return values[name],1
            with patch('winreg.QueryValueEx',side_effect=query):
                expected=set()
                for value in values.values():expected.update(value if isinstance(value,list) else [value])
                self.assertEqual(interface_guids(object()),expected)


if __name__=='__main__':unittest.main()
