import unittest,os
from unittest.mock import patch,Mock
from PIL import Image
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
try:
 from PySide6.QtWidgets import QApplication,QSystemTrayIcon
 from PySide6.QtTest import QTest
 from rio_monitor.qt_app import Bridge,Frames,preview_bytes
 from rio_monitor.settings import Settings
except ImportError:
 QApplication=None
class Weather:
 location=None
 def __init__(self):self.configure=Mock()
@unittest.skipIf(QApplication is None,'Qt not installed')
class BridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):self.b=Bridge(self.app,Settings(),Weather(),Frames(),capture=True)
 def tearDown(self):self.b.save_timer.stop();self.b.storage.close()
 def test_settings_save(self):
  self.b.setLanguage('zh');self.b.setRotation(90);self.b.setAutostart(True)
  self.assertEqual(self.b.s.rotation,90);self.assertTrue(self.b.s.autostart);self.assertEqual(self.b.s.language,'zh')
 def test_shared_footer_returns_to_download_after_driver_or_media_work(self):
  from rio_monitor.updater import AutoUpdater
  self.b.setLanguage('zh')
  updater=AutoUpdater('unused-updates');self.b.updater=updater
  with patch.object(updater,'check',side_effect=lambda:updater.update(state='checking')) as check:
   self.b.checkUpdates();check.assert_called_once();self.assertEqual(self.b.updateState,'checking')
  updater.update(state='downloading',connection='connected',progress=42);self.b.consume()
  self.assertAlmostEqual(self.b.footerProgress,.42);self.assertTrue(self.b.footerBusy)
  self.b.monitor.busy=True;self.b.monitor.operation='installing';self.b.changed.emit()
  self.assertEqual(self.b.footerProgress,-1);self.assertIn('安装',self.b.footerStatus)
  self.b.monitor.operation='uninstalling';self.assertIn('卸载',self.b.footerStatus)
  self.b.monitor.busy=False;self.b.storage.update(busy=True,phase='write',progress=.37)
  self.assertAlmostEqual(self.b.footerProgress,.37);self.assertIn('写入',self.b.footerStatus)
  self.b.storage.update(busy=False);self.assertAlmostEqual(self.b.footerProgress,.42)
  self.b.setLanguage('en');self.assertEqual(self.b.footerStatus,'Downloading…')
  updater.update(state='ready',progress=100);self.b.consume()
  self.assertFalse(self.b.footerBusy);self.assertEqual(self.b.footerStatus,'Restarting…')
  updater.update(state='latest');self.b.consume();self.assertEqual(self.b.footerStatus,'');self.assertFalse(self.b.footerBusy)
  self.b.setLanguage('zh');self.assertEqual(self.b.footerStatus,'')
 def test_verified_update_exits_once_after_existing_jobs_finish(self):
  from rio_monitor.updater import AutoUpdater
  self.b.capture=False;self.b.updater=AutoUpdater('unused-updates')
  with patch.object(self.b,'exit') as exit:
   for state in ('checking','downloading','error'):
    self.b.updater.update(state=state);self.b.consume()
   exit.assert_not_called()
   self.b.updater.update(state='ready',progress=100);self.b.storage.update(busy=True)
   self.b.consume();exit.assert_not_called()
   self.b.storage.update(busy=False);self.b.monitor.busy=True
   self.b.consume();exit.assert_not_called()
   self.b.monitor.busy=False;self.b.consume();self.b.consume();exit.assert_called_once()
 def test_installed_module_updates_restart_once_blackshark_is_idle(self):
  from rio_monitor.updater import AutoUpdater
  self.b.capture=False;self.b.updater=AutoUpdater('unused-updates');self.b.updater.update(state='latest')
  shark=Mock();shark.runtime.snapshot.return_value={'busy':True};self.b.blackshark_module=shark
  with patch.object(self.b,'exit') as exit:
   self.b.consume();exit.assert_not_called()
   self.b.updater.restart=True;self.b.consume();exit.assert_not_called();self.assertFalse(self.b.updater.relaunch)
   shark.runtime.snapshot.return_value={'busy':False};self.b.consume();self.b.consume()
   exit.assert_called_once();self.assertTrue(self.b.updater.relaunch)
  self.b.blackshark_module=None
 def test_rotation_applies_before_debounced_save_without_weather_restart(self):
  self.b.capture=False
  with patch('rio_monitor.qt_app.save') as save:
   self.b.setRotation(35);self.b.setRotation(90)
   self.assertEqual(self.b.s.rotation,90);save.assert_not_called()
   QTest.qWait(350)
   save.assert_called_once();self.assertEqual(save.call_args.args[0].rotation,90)
  self.b.weather.configure.assert_not_called()
 def test_save_hides_only_after_settings_are_persisted(self):
  self.b.capture=False;self.b.win=Mock();self.b.tray=Mock();self.b.tray.isVisible.return_value=True
  self.b.setRotation(39)
  with patch('rio_monitor.qt_app.save',side_effect=OSError('Disk full')):
   self.b.saveAndHide();self.b.win.hide.assert_not_called();self.assertTrue(self.b._dirty)
  with patch('rio_monitor.qt_app.save') as save:
   self.b.saveAndHide();save.assert_called_once();self.b.win.hide.assert_called_once()
 def test_autostart_failure_keeps_previous_state(self):
  self.b.capture=False
  with patch('rio_monitor.qt_app.set_autostart',side_effect=OSError('Access denied')):
   self.b.setAutostart(True)
  self.assertFalse(self.b.s.autostart);self.assertFalse(self.b._dirty);self.assertIn('Access denied',self.b.notice)
 def test_already_enabled_autostart_refreshes_moved_program_path_without_saving_preferences(self):
  self.b.s.autostart=True;self.b.capture=False
  with patch('rio_monitor.qt_app.set_autostart') as register,patch('rio_monitor.qt_app.save') as save:
   self.b.setAutostart(True);register.assert_called_once_with(True)
   self.assertTrue(self.b.s.autostart);self.assertFalse(self.b._dirty);save.assert_not_called()
 def test_close_flushes_pending_rotation_without_waiting(self):
  self.b.capture=False;self.b.win=Mock();self.b.tray=Mock();self.b.tray.isVisible.return_value=True
  with patch('rio_monitor.qt_app.save') as save:
   self.b.setRotation(180);self.b.hideWindow();save.assert_called_once()
  self.b.win.hide.assert_called_once();self.assertFalse(self.b.save_timer.isActive())
 def test_transparent_preview_does_not_modify_usb_frame(self):
  frame=Image.new('RGB',(480,480),(12,34,56));preview=Image.frombytes('RGBA',frame.size,preview_bytes(frame))
  self.assertEqual(preview.getpixel((0,0))[3],0);self.assertEqual(preview.getpixel((240,240)),(12,34,56,255))
  self.assertEqual(frame.mode,'RGB');self.assertEqual(frame.getpixel((0,0)),(12,34,56))
 def test_city_selection_cancels_older_requests(self):
  self.b._results=[dict(name='Test',label='Test, Region',latitude=10,longitude=20)]
  self.b.selectCity(0);self.assertEqual(self.b.mode,'manual');self.assertEqual(self.b.cityLabel,'Test');self.assertEqual(self.b.generation,1)
  self.assertEqual(self.b.s.weather_mode,'manual');self.b.weather.configure.assert_called_once()
  self.b.mail.put(('locate',0,{'latitude':1,'longitude':2,'city':'Wrong'},None));self.b.consume();self.assertEqual(self.b.cityLabel,'Test')
 def test_bad_search_row_does_not_crash(self):
  self.b.mail.put(('search',0,[{'name':'Invalid','latitude':'x','longitude':0}],None));self.b.consume();self.assertEqual(self.b.cityResults,[])
 def test_unavailable_tray_stays_recoverable(self):
  # In production a missing tray must not hide the only recoverable UI.
  self.b.capture=False;self.b.hideWindow();self.assertIn('System tray unavailable',self.b.notice)
 def test_tray_right_click_opens_menu_and_left_click_opens_settings(self):
  self.b.menu=Mock();self.b.win=Mock()
  self.b.trayActivated(QSystemTrayIcon.Context)
  self.b.menu.popup.assert_called_once();self.b.menu.activateWindow.assert_called_once()
  self.b.win.show.assert_not_called()
  self.b.trayActivated(QSystemTrayIcon.Trigger);self.b.win.show.assert_called_once()
 def test_reset_requires_pending_request_and_acceptance(self):
  from pathlib import Path
  from tempfile import TemporaryDirectory
  self.b.capture=False
  with TemporaryDirectory() as td, patch.object(self.b.storage,'prepare') as prepare:
   self.b.storage.assets=Path(td)
   Image.new('RGB',(480,480)).save(self.b.storage.assets/'default-screen.gif','GIF')
   self.b.confirmRestoreDefault(True);prepare.assert_not_called()
   self.b.requestRestoreDefault();self.assertTrue(self.b.defaultConfirmation);prepare.assert_not_called()
   self.b.confirmRestoreDefault(False);self.assertFalse(self.b.defaultConfirmation);prepare.assert_not_called()
   self.b.requestRestoreDefault();self.b.confirmRestoreDefault(True)
   prepare.assert_called_once_with(self.b.storage.assets/'default-screen.gif',write_after=True)
   self.b.confirmRestoreDefault(True);prepare.assert_called_once()
 def test_open_preview_uses_stored_content_without_preparing_default_or_writing(self):
  with patch.object(self.b.storage,'open_preview') as opened, patch.object(self.b.storage,'prepare') as prepare, patch.object(self.b.storage,'write') as write:
   self.b.prepareStoragePreview();opened.assert_called_once();prepare.assert_not_called();write.assert_not_called()
   self.assertIsNone(self.b.storage.session.output)
