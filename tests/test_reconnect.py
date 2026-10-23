import io,threading,unittest
from unittest.mock import Mock,patch
from PIL import Image
from rio_monitor.output import ScreenOutput
from rio_monitor.resources import pack_resource
from rio_monitor.storage import DisplaySession


class Writer:
    def __init__(self,path):
        self.path=path;self.error=None;self.sent=0;self.finished=threading.Event();self.closed=False;self.can_close=True
    def close(self):
        if not self.can_close:return False
        self.closed=True;self.finished.set();return True
    def submit(self,frame):self.sent+=1


class ReconnectTests(unittest.TestCase):
    def test_missing_device_retries_with_backoff_then_connects_new_path(self):
        paths=[];created=[]
        def factory(path):
            writer=Writer(path);created.append(writer);return writer
        session=DisplaySession(enumerator=lambda:list(paths),output_factory=factory)
        for now,attempts in [(0,1),(.9,1),(1,2),(2.9,2),(3,3),(6.9,3),(7,4),(11.9,4),(12,5)]:
            session.reconnect(now);self.assertEqual(session.connection_attempts,attempts)
        self.assertEqual(session.retry_delay,5);self.assertFalse(created)
        paths.append('replugged-path');session.reconnect(17)
        self.assertEqual(created[0].path,'replugged-path');self.assertIsNone(session.snapshot()['usb_error'])
        session.submit(Image.new('RGB',(480,480)));session.reconnect(17.1)
        self.assertEqual(session.retry_delay,1);self.assertEqual(session.retry_at,0);self.assertTrue(session.close())

    def test_failed_worker_frees_old_handle_before_new_path_opens(self):
        old=Writer('old');old.error='disconnected';created=[]
        def factory(path):
            self.assertTrue(old.closed);writer=Writer(path);created.append(writer);return writer
        session=DisplaySession(enumerator=lambda:['new'],output_factory=factory);session.output=old
        session.reconnect(0);self.assertFalse(created);self.assertFalse(old.closed)
        old.finished.set();session.reconnect(.2)
        self.assertEqual(created[0].path,'new');self.assertTrue(session.close())

    def test_old_handle_refusing_close_prevents_a_second_owner(self):
        old=Writer('old');old.error='failed';old.finished.set();old.can_close=False
        factory=Mock();session=DisplaySession(enumerator=lambda:['new'],output_factory=factory);session.output=old
        session.reconnect(0);session.reconnect(1)
        factory.assert_not_called();self.assertIn('has not stopped',session.error)
        old.can_close=True;self.assertTrue(session.close())

    def test_resource_write_and_stored_playback_suspend_live_reconnect(self):
        buffer=io.BytesIO();Image.new('RGB',(480,480),'red').save(buffer,'GIF')
        active=threading.Event();release=threading.Event();errors=[];factory=Mock();transport=Mock()
        session=DisplaySession(enumerator=lambda:['device'],output_factory=factory,transport_factory=lambda path:transport)
        def upload(*args):active.set();release.wait(2)
        def replace():
            try:session.replace(pack_resource(buffer.getvalue()),lambda *args:None)
            except Exception as exc:errors.append(str(exc))
        with patch('rio_monitor.storage.ResourceSender') as sender:
            sender.return_value.upload.side_effect=upload;worker=threading.Thread(target=replace);worker.start()
            try:
                self.assertTrue(active.wait(1));session.reconnect(0);self.assertFalse(session.close());factory.assert_not_called()
            finally:release.set();worker.join(2)
        self.assertFalse(errors);self.assertFalse(worker.is_alive());self.assertEqual(session.mode,'stored')
        session.reconnect(10);factory.assert_not_called();self.assertTrue(session.close())

    def test_failed_live_recovery_remains_eligible_when_device_returns(self):
        paths=[];session=DisplaySession('stored',enumerator=lambda:list(paths),output_factory=Writer)
        with self.assertRaises(RuntimeError):session.connect()
        self.assertEqual(session.mode,'monitor')
        paths.append('returned');session.reconnect(0);self.assertTrue(session.live);self.assertTrue(session.close())

    def test_background_start_is_idempotent_and_exit_prevents_reopening(self):
        opened=threading.Event();created=[]
        def factory(path):
            writer=Writer(path);created.append(writer);opened.set();return writer
        session=DisplaySession(enumerator=lambda:['device'],output_factory=factory)
        try:
            session.start();session.start();self.assertTrue(opened.wait(1))
        finally:self.assertTrue(session.close())
        self.assertFalse(session.thread.is_alive());self.assertTrue(created[0].closed)
        session.reconnect(100);self.assertEqual(len(created),1)
        with self.assertRaisesRegex(RuntimeError,'closed'):session.connect()

    def test_finished_flag_waits_until_transport_is_released_after_query_error(self):
        entered=threading.Event();release=threading.Event();transport=Mock();sender=Mock()
        sender.lcd_info.side_effect=OSError('device gone')
        def close():entered.set();release.wait(2)
        transport.close.side_effect=close
        with patch('rio_monitor.output.WinUSB',return_value=transport),patch('rio_monitor.output.FrameSender',return_value=sender):
            output=ScreenOutput('device')
            try:
                self.assertTrue(entered.wait(1));self.assertFalse(output.finished.is_set())
            finally:release.set();self.assertTrue(output.close())
        self.assertTrue(output.finished.is_set());self.assertEqual(output.error,'device gone')
        transport.close.assert_called_once();sender.send.assert_not_called()
