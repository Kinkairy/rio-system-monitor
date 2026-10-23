import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from rio_monitor.media import prepare_media
from rio_monitor.storage import StorageJob, DisplaySession
from rio_monitor.stored_preview import StoredPreviewCache
from rio_monitor.resources import ResourceSender, QUERY
from rio_monitor.protocol import ProtocolError
from test_storage import Transport, gif


class StoredPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'chosen.gif'
        self.source.write_bytes(gif())
        self.media = prepare_media(self.source, self.root / 'prepared', Path('no-converter'))
        self.cache = StoredPreviewCache(self.root / 'cache')

    def tearDown(self):
        self.temp.cleanup()

    def test_cache_is_device_bound_and_survives_restart(self):
        self.cache.store('device-A', self.media)
        again = StoredPreviewCache(self.root / 'cache')
        self.assertEqual(again.load('device-a').gif, self.media.gif)
        self.assertIsNone(again.load('device-B'))
        _, _, preview = self.cache.paths('device-A')
        preview.write_bytes(b'corrupted')
        self.assertIsNone(again.load('device-A'))

    def test_open_uses_last_successful_write_and_selection_is_only_a_preview(self):
        self.cache.store('device', self.media)
        session = DisplaySession(enumerator=lambda: ['device'])
        session.replace = Mock()
        job = StorageJob(session, Path(), self.root / 'cache')
        self.addCleanup(job.close)
        job.open_preview()
        self.assertEqual(Path(job.snapshot()['preview']).read_bytes(), self.media.gif)
        self.assertFalse(job.snapshot()['ready'])
        selected = self.root / 'new.png'
        Image.new('RGB', (480, 480), 'blue').save(selected)
        job.prepare(selected); job.thread.join(5)
        self.assertEqual(job.snapshot()['name'], 'new.png')
        self.assertNotEqual(job.prepared.gif, self.media.gif)
        self.assertEqual(self.cache.load('device').gif, self.media.gif)
        session.replace.assert_not_called()
        job.open_preview()
        self.assertEqual(job.snapshot()['name'], 'chosen.gif')

    def test_unknown_storage_does_not_fall_back_to_default(self):
        session = DisplaySession(enumerator=lambda: ['unknown'])
        job = StorageJob(session, self.root, self.root / 'cache')
        self.addCleanup(job.close)
        (self.root / 'default-screen.gif').write_bytes(self.media.gif)
        job.open_preview()
        self.assertEqual(job.snapshot()['preview'], '')
        self.assertFalse(job.snapshot()['ready'])

    def test_successful_upload_records_preview_and_failed_upload_does_not(self):
        transport = Transport()
        session = DisplaySession(enumerator=lambda: ['device'], transport_factory=lambda path: transport)
        job = StorageJob(session, Path(), self.root / 'cache')
        self.addCleanup(job.close)
        job.prepare(self.source); job.thread.join(5)
        self.assertTrue(job.write()); job.thread.join(5)
        self.assertEqual(job.snapshot()['phase'], 'stored')
        self.assertEqual(self.cache.load('device').gif, self.media.gif)
        # A bad identity query changes no storage and preserves the known cache.
        transport.fail = 'tag'
        job.prepare(self.source); job.thread.join(5); job.write(); job.thread.join(5)
        self.assertEqual(job.snapshot()['phase'], 'error')
        self.assertEqual(self.cache.load('device').gif, self.media.gif)

    def test_cache_is_invalidated_before_any_erase_even_if_ack_fails(self):
        class RejectErase(Transport):
            def read(self, ep, count):
                if self.commands[-1] != QUERY:
                    self.fail = 'tag'
                return super().read(ep, count)
        self.cache.store('device', self.media)
        session = DisplaySession(enumerator=lambda: ['device'], transport_factory=lambda path: RejectErase())
        with self.assertRaises(ProtocolError):
            session.replace(self.media.blob, lambda *args: None, before_erase=self.cache.invalidate)
        self.assertIsNone(self.cache.load('device'))

    def test_invalidating_cache_failure_stops_before_erase(self):
        transport = Transport()
        def fail():
            raise OSError('Cache is read-only')
        with self.assertRaises(OSError):
            ResourceSender(transport).upload(self.media.blob, before_erase=fail)
        self.assertEqual(transport.commands, [QUERY])

    def failure_job(self, mode='monitor', recovery_error=None):
        session=Mock(mode=mode)
        session.replace.side_effect=ProtocolError('Rejected upload')
        if recovery_error:session.connect.side_effect=recovery_error
        job=StorageJob(session, Path());self.addCleanup(job.close)
        job.prepare(self.source);job.thread.join(5);job.write();job.thread.join(5)
        return job,session

    def test_failed_upload_restores_previous_real_time_output(self):
        job,session=self.failure_job()
        session.connect.assert_called_once()
        self.assertEqual(job.snapshot()['phase'],'error')
        self.assertFalse(job.snapshot()['writing'])
        self.assertIn('Rejected upload',job.snapshot()['error'])

    def test_failed_upload_does_not_override_a_previous_stored_mode(self):
        job,session=self.failure_job('stored')
        session.connect.assert_not_called()

    def test_failed_recovery_keeps_the_original_error_and_stops_busy_state(self):
        job,session=self.failure_job(recovery_error=OSError('Disconnected'))
        self.assertIn('Rejected upload',job.snapshot()['error'])
        self.assertIn('Disconnected',job.snapshot()['error'])
        self.assertFalse(job.snapshot()['busy'])

    def test_cache_save_failure_does_not_undo_a_successful_upload(self):
        session=DisplaySession(enumerator=lambda:['device'],transport_factory=lambda path:Transport())
        job=StorageJob(session,Path(),self.root/'cache');self.addCleanup(job.close)
        job.prepare(self.source);job.thread.join(5)
        with patch.object(job.cache,'store',side_effect=OSError('Cache read-only')):
            job.write();job.thread.join(5)
        self.assertEqual(job.snapshot()['phase'],'stored')
        self.assertEqual(session.mode,'stored')
        self.assertIn('Cache read-only',job.snapshot()['preview_cache_error'])
        self.assertIsNone(self.cache.load('device'))
