"""Fixed package + captured loader replies; no hardware access."""
import copy,json,os,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from rio_monitor import firmware_update as fw
from rio_monitor.storage import DisplaySession

class Port:
    def __init__(self,replies,short_at=None):
        self.replies=copy.deepcopy(replies);self.sent=[];self.buffer=b'';self.short_at=short_at;self.closed=False
    @property
    def in_waiting(self):return len(self.buffer)
    def write(self,data):
        self.sent.append(data);self.buffer=bytes.fromhex(self.replies[len(self.sent)-1]) if len(self.sent)<=len(self.replies) else b''
        return len(data)-(1 if len(self.sent)==self.short_at else 0)
    def read(self,n):
        # Fragmented serial reads must still produce one complete 63B reply.
        data=self.buffer[:min(n,7)];self.buffer=self.buffer[len(data):];return data
    def close(self):self.closed=True

class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=os.environ.get('RIO_LT168B_FIRMWARE_DIR')
        if not folder:raise unittest.SkipTest('Pinned private firmware build input required')
        cls.folder=Path(folder);cls.plan=fw.load_plan(cls.folder)
        cls.fixture=json.loads((Path(__file__).parent/'fixtures/lt168b-boot-replies.json').read_text())
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.replies=list(self.fixture['replies']);self.port=Port(self.replies)
    def service(self,paths=lambda:[],ports=lambda:['COM_TEST']):
        session=DisplaySession(enumerator=paths)
        service=fw.FirmwareUpdate(session,self.folder,Path(self.tmp.name),ports=ports,opener=Mock(return_value=self.port),detector=lambda:['stock'])
        return service,session
    def test_success_uses_accepted_payload_and_stock_preflight_then_runs_after_checks(self):
        import hashlib
        events=[];progress=[];fw.program(self.port,self.plan,events.append,progress.append)
        self.assertEqual([hashlib.sha256(p).hexdigest() for p in self.port.sent],self.fixture['tx_sha256'])
        self.assertEqual(len(self.port.sent),14);self.assertEqual(self.port.sent[-1],b'\x4f'+bytes(63));self.assertEqual(progress[-1],1)
        self.assertEqual(events[-2]['state'],'sending');self.assertEqual(events[-3]['name'],'verify_following_sector')
    def test_tampered_package_refused(self):
        p=Path(self.tmp.name)/'em133-v3-rio1.json';p.write_bytes((self.folder/p.name).read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'checksum'):fw.load_plan(p.parent)
    def test_wrong_identity_or_original_firmware_never_enters_programming_mode(self):
        for index,offset in ((0,1),(0,5),(0,9),(0,13),(1,1),(1,5),(2,1),(2,5)):
            with self.subTest(index=index,offset=offset):
                replies=list(self.replies);b=bytearray.fromhex(replies[index]);b[offset]^=1;replies[index]=b.hex();p=Port(replies)
                with self.assertRaises(OSError):fw.program(p,self.plan)
                self.assertLessEqual(len(p.sent),3);self.assertFalse(any(v[:2]==b'K1' for v in p.sent))
    def test_bad_opcode_status_offset_or_post_write_crc_stops_without_run_or_retry(self):
        for index,offset in ((3,0),(4,1),(5,1),(6,2),(11,1),(12,1),(12,5)):
            with self.subTest(index=index,offset=offset):
                replies=list(self.replies);b=bytearray.fromhex(replies[index]);b[offset]^=1;replies[index]=b.hex();p=Port(replies)
                with self.assertRaises(OSError):fw.program(p,self.plan)
                self.assertEqual(len(p.sent),index+1);self.assertFalse(any(v[0]==0x4f for v in p.sent))
    def test_short_write_not_retried(self):
        p=Port(self.replies,short_at=6)
        with self.assertRaisesRegex(OSError,'Short'):fw.program(p,self.plan)
        self.assertEqual(len(p.sent),6)
    def test_pending_input_refused_without_commands(self):
        self.port.buffer=b'x'
        with self.assertRaisesRegex(OSError,'pending'):fw.program(self.port,self.plan)
        self.assertEqual(self.port.sent,[])
    def test_read_timeout_stops_before_program_mode(self):
        p=Port(['']);clock=iter([0,11])
        with patch.object(fw.time,'monotonic',side_effect=lambda:next(clock)):
            with self.assertRaisesRegex(OSError,'reply'):fw.program(p,self.plan)
        self.assertEqual(len(p.sent),1)
    def test_cancel_before_program_mode(self):
        with self.assertRaisesRegex(RuntimeError,'cancelled'):fw.program(self.port,self.plan,cancelled=lambda:True)
        self.assertEqual(self.port.sent,[])
    def test_only_matching_stock_is_offered_and_never_arms_itself(self):
        service,session=self.service();session.output=SimpleNamespace(path='stock')
        for protocol in ('rio-winusb','lt168b-rio-bench','unknown'):self.assertFalse(service.offer(protocol))
        service.detector=lambda:['different'];self.assertFalse(service.offer('levetop-emonitor'))
        service.detector=lambda:['stock'];self.assertTrue(service.offer('levetop-emonitor'))
        self.assertEqual(service.snapshot()['state'],'available');self.assertFalse(service.snapshot()['busy']);service.opener.assert_not_called()
        service.dismiss();self.assertFalse(service.offer('levetop-emonitor'))
        service.offer('rio-winusb');self.assertFalse(service.offer('levetop-emonitor'))
        # A real observed unplug re-arms even if the same USB path/protocol returns.
        session._enumerator=lambda:[]
        with self.assertRaises(RuntimeError):session.one_path()
        self.assertTrue(service.offer('levetop-emonitor'))
    def test_descriptor_profile_is_exact_not_vendor_only(self):
        good=dict(path=b'stock',vendor_id=0xeeef,product_id=0x1616,manufacturer_string='LEVETOP',product_string='USB-HID',release_number=256,usage_page=1,usage=0,interface_number=0)
        devices=[good]+[dict(good,**{k:'wrong'}) for k in good if k!='path']
        with patch.dict('sys.modules',{'hid':SimpleNamespace(enumerate=lambda *a:devices)}):self.assertEqual(fw.stock_paths(),['stock'])
    def test_wait_cancel_releases_session_without_writes(self):
        service,session=self.service(ports=lambda:[]);service.update(state='available');self.assertTrue(service.start());self.assertFalse(service.start())
        service.dismiss();self.assertTrue(service.close());service.opener.assert_not_called();self.assertEqual(session.mode,'monitor')
    def test_cancel_at_port_open_does_not_cross_write_boundary(self):
        service,session=self.service()
        def opened(name):service.cancel_event.set();return self.port
        service.opener=opened;service._run()
        self.assertEqual(service.snapshot()['state'],'cancelled');self.assertEqual(self.port.sent,[]);self.assertTrue(self.port.closed)
    def test_manual_preview_and_running_app_do_not_write(self):
        journal=Path(self.tmp.name)/'manual.json'
        with patch.object(fw,'boot_ports',return_value=['COM_TEST']),patch.object(fw,'open_port') as opened,patch('rio_monitor.display_protocols.enumerate_paths',return_value=[]),patch('rio_monitor.settings.acquire_instance',return_value=None):
            self.assertEqual(fw.main(['--firmware-dir',str(self.folder),'--journal',str(journal),'--write-em133-v3']),1);opened.assert_not_called()
        journal=Path(self.tmp.name)/'preview.json'
        with patch.object(fw,'boot_ports',return_value=['COM_TEST']),patch.object(fw,'open_port') as opened,patch('rio_monitor.display_protocols.enumerate_paths',return_value=[]),patch('rio_monitor.settings.acquire_instance',return_value=True):
            self.assertEqual(fw.main(['--firmware-dir',str(self.folder),'--journal',str(journal)]),0);opened.assert_not_called()
        self.assertEqual(json.loads(journal.read_text())['result'],'preview_only_no_device_commands')
    def test_ambiguous_or_other_screen_refused(self):
        for ports,paths in ((lambda:['A','B'],lambda:[]),(lambda:['A'],lambda:['normal'])):
            service,session=self.service(paths,ports);service._run()
            self.assertEqual(service.snapshot()['state'],'error');service.opener.assert_not_called();self.assertEqual(session.mode,'monitor')
    def test_previous_worker_must_close_before_boot_open(self):
        service,session=self.service();session.output=Mock();session.output.close.return_value=False;service._run()
        service.opener.assert_not_called();self.assertEqual(service.snapshot()['state'],'error')
    def test_worker_success_journals_then_resumes_monitor(self):
        service,session=self.service();session.output=Mock();session.output.close.return_value=True
        service._run();self.assertEqual(service.snapshot()['state'],'done');self.assertFalse(service.snapshot()['busy']);self.assertTrue(self.port.closed)
        self.assertEqual(session.mode,'monitor');self.assertIsNone(session.output)
        journal=json.loads(next(Path(self.tmp.name).glob('*.json')).read_text());self.assertIsNone(journal['error']);self.assertEqual(journal['image_sha256'],fw.IMAGE_SHA)
    def test_worker_failure_resumes_without_retry_and_records_error(self):
        service,session=self.service();self.port.short_at=6;service._run()
        self.assertEqual(service.snapshot()['state'],'error');self.assertEqual(len(self.port.sent),6);self.assertTrue(self.port.closed);self.assertEqual(session.mode,'monitor')
    def test_screen_owner_rejects_reconnect_media_and_close_while_writing(self):
        service,session=self.service();session.mode='firmware';service.update(state='writing',busy=True)
        self.assertFalse(service.close());self.assertFalse(session.close())
        with self.assertRaisesRegex(RuntimeError,'firmware'):session.connect()
        session.reconnect();self.assertEqual(session.connection_attempts,0)
        from tests.test_storage import gif
        from rio_monitor.resources import pack_resource
        with self.assertRaisesRegex(RuntimeError,'firmware'):session.replace(pack_resource(gif()),lambda *a:None)

class FirmwareBridgeTests(unittest.TestCase):
    def test_transient_firmware_mode_is_never_saved(self):
        from PySide6.QtWidgets import QApplication
        from rio_monitor.qt_app import Bridge,Frames
        from rio_monitor.settings import Settings
        app=QApplication.instance() or QApplication([])
        b=Bridge(app,Settings(),SimpleNamespace(location=None),Frames(),capture=True)
        try:
            b.storage.session.mode='firmware';b.consume();self.assertEqual(b.s.display_mode,'monitor')
            with patch.object(b.firmware,'start') as start:b.startFirmware();start.assert_not_called()
        finally:b.save_timer.stop();b.storage.close()

class BootDiscoveryTests(unittest.TestCase):
    def port(self,name='COM6',serial='',vid=0xeeef,pid=0x268a):
        return SimpleNamespace(device=name,serial_number=serial,vid=vid,pid=pid)
    def test_dotted_serial_uses_exact_present_fallback(self):
        with patch('serial.tools.list_ports.comports',return_value=[self.port(),self.port('COM7','wrong'),self.port('COM8',vid=1)]),patch.object(fw,'_windows_boot_port',return_value='COM6') as exact:
            self.assertEqual(fw.boot_ports(),['COM6']);exact.assert_called_once()
    def test_missing_wrong_or_stale_identity_is_not_vendor_only_match(self):
        for exact in (None,'COM7'):
            with patch('serial.tools.list_ports.comports',return_value=[self.port()]),patch.object(fw,'_windows_boot_port',return_value=exact):
                self.assertEqual(fw.boot_ports(),[])
        with patch('serial.tools.list_ports.comports',return_value=[self.port(serial='WRONG')]),patch.object(fw,'_windows_boot_port',return_value='COM6') as exact:
            self.assertEqual(fw.boot_ports(),[]);exact.assert_not_called()
    def test_existing_serial_and_multiple_matching_ports_are_preserved(self):
        with patch('serial.tools.list_ports.comports',return_value=[self.port(serial='TEST_1.0'),self.port('COM7','TEST_1.0')]),patch.object(fw,'_windows_boot_port') as exact:
            self.assertEqual(fw.boot_ports(),['COM6','COM7']);exact.assert_not_called()
    def fake(self,locate=0,status=8,problem=0):
        api=SimpleNamespace(CM_Locate_DevNodeW=Mock(return_value=locate),CM_Get_DevNode_Status=Mock())
        def fill(s,p,n,f):s._obj.value=status;p._obj.value=problem;return 0
        api.CM_Get_DevNode_Status.side_effect=fill
        reg=SimpleNamespace(HKEY_LOCAL_MACHINE=1,REG_SZ=1,OpenKey=Mock(),QueryValueEx=Mock(return_value=('COM6',1)))
        reg.OpenKey.return_value.__enter__=Mock(return_value='key');reg.OpenKey.return_value.__exit__=Mock(return_value=False)
        return api,reg
    def test_native_exact_instance_flags_and_registry_port(self):
        api,reg=self.fake()
        with patch.object(fw.sys,'platform','win32'):self.assertEqual(fw._windows_boot_port(api,reg),'COM6')
        self.assertEqual(api.CM_Locate_DevNodeW.call_args.args[1:],(r'USB\VID_EEEF&PID_268A\TEST_1.0',0))
        self.assertEqual(reg.OpenKey.call_args.args[1],r'SYSTEM\CurrentControlSet\Enum\USB\VID_EEEF&PID_268A\TEST_1.0\Device Parameters')
    def test_no_phantom_disabled_or_problem_nodes(self):
        for locate,status in ((13,8),(0,0),(0,0x408)):
            api,reg=self.fake(locate,status)
            with patch.object(fw.sys,'platform','win32'):self.assertIsNone(fw._windows_boot_port(api,reg))
            reg.OpenKey.assert_not_called()
    def test_native_errors_and_bad_port_fail_closed(self):
        api,reg=self.fake(locate=5)
        with patch.object(fw.sys,'platform','win32'),self.assertRaises(OSError):fw._windows_boot_port(api,reg)
        for value,kind in (('COM0',1),('COM6junk',1),('LPT1',1),('COM6',2)):
            api,reg=self.fake();reg.QueryValueEx.return_value=(value,kind)
            with patch.object(fw.sys,'platform','win32'):self.assertIsNone(fw._windows_boot_port(api,reg))
    def test_nonwindows_does_not_use_registry(self):
        api,reg=self.fake()
        with patch.object(fw.sys,'platform','linux'):self.assertIsNone(fw._windows_boot_port(api,reg))
        api.CM_Locate_DevNodeW.assert_not_called();reg.OpenKey.assert_not_called()

if __name__=='__main__':unittest.main()
