import unittest,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
try:
 from PySide6.QtWidgets import QApplication
 from rio_monitor.qt_app import Bridge,Frames
 from rio_monitor.settings import Settings
except ImportError:
 QApplication=None
class Weather:
 location=None
 def configure(self,s,loc):self.s=s;self.loc=loc
@unittest.skipIf(QApplication is None,'Qt not installed')
class BridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):self.b=Bridge(self.app,Settings(),Weather(),Frames(),capture=True)
 def test_settings_save(self):
  self.b.setLanguage('zh');self.b.saveSettings(90,True,True)
  self.assertEqual(self.b.s.rotation,90);self.assertTrue(self.b.s.autostart);self.assertTrue(self.b.s.start_hidden);self.assertEqual(self.b.s.language,'zh')
 def test_city_selection_cancels_older_requests(self):
  self.b._results=[dict(name='Test',label='Test, Region',latitude=10,longitude=20)]
  self.b.selectCity(0);self.assertEqual(self.b.mode,'manual');self.assertEqual(self.b.cityLabel,'Test');self.assertEqual(self.b.generation,1)
  self.b.mail.put(('locate',0,{'latitude':1,'longitude':2,'city':'Wrong'},None));self.b.consume();self.assertEqual(self.b.cityLabel,'Test')
 def test_bad_search_row_does_not_crash(self):
  self.b.mail.put(('search',0,[{'name':'Invalid','latitude':'x','longitude':0}],None));self.b.consume();self.assertEqual(self.b.cityResults,[])
 def test_unavailable_tray_stays_recoverable(self):
  # In production a missing tray must not hide the only recoverable UI.
  self.b.capture=False;self.b.hideWindow();self.assertIn('System tray unavailable',self.b.notice)
