import unittest,time
from rio_monitor.weather_source import WeatherWorker
from rio_monitor.settings import Settings
class SourceTests(unittest.TestCase):
 def wait(self,w):
  end=time.monotonic()+2
  while time.monotonic()<end:
   if w.reading is not None or 'unavailable' in w.status:return
   time.sleep(.01)
 def test_off_makes_no_network_requests(self):
  calls=[];w=WeatherWorker(Settings(weather_mode='off'),lambda u:calls.append(u));time.sleep(.03);w.close();self.assertEqual(calls,[])
 def test_auto_validates_and_maps(self):
  calls=[]
  def fetch(u):
   calls.append(u)
   if 'ipwho.is' in u:return {'success':True,'city':'Test','latitude':12.345,'longitude':34.567}
   return {'current':{'temperature_2m':24,'weather_code':3,'time':time.time()}}
  w=WeatherWorker(Settings(weather_mode='auto'),fetch);self.wait(w);w.close()
  self.assertEqual(w.reading.kind,'cloud');self.assertEqual(w.reading.temperature,24)
  self.assertIn('latitude=12.35',calls[1]);self.assertNotIn('ip=',calls[1])
 def test_stale_response_is_not_current(self):
  def fetch(u):
   if 'ipwho.is' in u:return {'success':True,'city':'Test','latitude':0,'longitude':0}
   return {'current':{'temperature_2m':24,'weather_code':3,'time':time.time()-4000}}
  w=WeatherWorker(Settings(weather_mode='auto'),fetch);self.wait(w);w.close();self.assertIsNone(w.reading)
