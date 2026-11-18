"""Check the released firmware workflow across the two physical USB re-enumerations."""
import hashlib
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rio_monitor import firmware_animation as update, firmware_release as fw, firmware_segments as seg
from rio_monitor import firmware_update

class Display:
    def __init__(self,release,initial,folder):
        self.release, self.head, self.folder=release, initial, folder
        self.gap=b''.join(hashlib.sha256(str(i).encode()).digest()*128 for i in range(len(seg.GAP_ENDS)))
        self.bank=bytearray(seg.BLANK)
        self.low_writes=[]
        self.usb=self
        self.next=self.seen=self.armed=self.phase=0
        self.buffer=b''
        self.chain=fw.CHAIN_ROOT
        self.drop_before_activation=False

    def identify(self):return seg.LOADER
    def checksum(self,end):
        tail=self.gap+self.bank+b'\xff'*seg.SECTOR
        return seg.crc(memoryview(tail)[:end-seg.LOW_END],self.head)
    def write_image(self,image,progress):
        assert image in (self.release.helper,self.release.player)
        self.head=seg.crc(image.data);self.low_writes.append(self.head)
    def run(self):pass
    def close(self):pass
    def maintenance(self):return update.Maintenance(self)
    def boot(self):
        if self.drop_before_activation:raise TimeoutError('button')
        return self
    def control(self,kind,request,value,i,size):
        assert value==0xb201
        if request==0x57:
            return b'RIOBK201'+fw.CHAIN_ROOT+struct.pack('<5I2B2x',self.seen,self.next,
                len(self.buffer),0,self.next,self.phase,self.armed)
        if request==0x58:
            assert kind==0xc0 and size==4096 and 0<=i<len(seg.GAP_ENDS)
            if i==self.seen:self.seen+=1
            return self.gap[i*seg.SECTOR:(i+1)*seg.SECTOR]
        assert kind==0x40 and not size
        if request==0x59:
            assert self.seen==len(seg.GAP_ENDS)
            assert next(self.folder.rglob('protected-588KiB.bin')).read_bytes()==self.gap
            self.armed=1
        elif request==0x5a:
            assert self.armed and i==self.next
            self.phase=1;self.buffer=b''
        elif request==0x5b:
            assert self.phase==1 and i==self.next and len(self.buffer)==seg.SECTOR+32
            assert hashlib.sha256(self.buffer).digest()==self.chain
            self.chain=self.buffer[-32:]
            self.bank[i*seg.SECTOR:(i+1)*seg.SECTOR]=self.buffer[:-32]
            self.next+=1;self.phase=0;self.buffer=b''
        else:raise AssertionError('Unexpected maintenance operation')
        return b''
    def write(self,ep,data):
        assert ep==1 and self.phase==1
        self.buffer=data
        return len(data)

class BuiltInFirmware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=os.environ.get('RIO_LT168B_FIRMWARE_DIR')
        if not folder or not (Path(folder)/fw.FILENAME).exists():
            raise unittest.SkipTest('Private RIO release input required')
        cls.inputs=Path(folder)
        cls.release=fw.bundled(folder)

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        self.events=[]
        self.screen=Display(self.release,update.FACTORY_CRC,self.folder)
        guard=patch.object(update,'FIRST_GUARD',seg.crc(self.screen.gap[:seg.SECTOR]))
        guard.start();self.addCleanup(guard.stop)

    def run_update(self,install=True):
        with patch.object(seg,'RioLoader',side_effect=lambda port:port):
            return update.run(self.screen,self.release,self.folder,install,self.events.append,
                              lambda state,p:None,self.screen)

    def test_factory_update_preserves_gap_and_current_screen_is_skipped(self):
        self.assertEqual(self.run_update(),'segments_verified_and_started')
        self.assertEqual(bytes(self.screen.bank),self.release.bank)
        self.assertEqual(self.run_update(),'already_installed_and_verified')
        self.assertEqual(self.screen.low_writes,[seg.crc(self.release.helper.data),seg.crc(self.release.player.data)])

    def test_both_earlier_rio_versions_are_offered_the_same_release(self):
        for old in self.release.previous:
            self.screen.head=seg.crc(old)
            self.assertEqual(self.run_update(False),'compatible_for_animation')
        self.assertFalse(self.screen.low_writes)

    def test_resume_after_second_button_timeout_writes_only_player(self):
        self.screen.drop_before_activation=True
        with self.assertRaises(TimeoutError):self.run_update()
        self.assertEqual(self.screen.low_writes,[seg.crc(self.release.helper.data)])
        self.assertEqual(self.run_update(),'segments_verified_and_started')
        self.assertEqual(self.events[-1]['stage'],'resumed_verified_bank')

    def test_different_flash_layout_or_occupied_bank_blocks_writes(self):
        self.screen.bank[0]=17
        with self.assertRaisesRegex(ValueError,'different image'):self.run_update()
        self.screen.bank[:]=seg.BLANK
        self.screen.gap=b'X'+self.screen.gap[1:]
        with self.assertRaisesRegex(ValueError,'layout'):self.run_update()
        self.assertFalse(self.screen.low_writes)

    def test_bundled_preview_runs_without_acquiring_the_screen(self):
        journal=self.folder/'preview.json'
        with patch('rio_monitor.settings.acquire_instance',side_effect=AssertionError):
            result=firmware_update.main(['--bundled-animation','--firmware-dir',str(self.inputs),'--journal',str(journal)])
        record=json.loads(journal.read_text())
        self.assertEqual((result,record['result'],record['animation_frames']),(0,'package_verified_offline',216))
