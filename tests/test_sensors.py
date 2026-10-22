import unittest
from rio_monitor.sensors import HardwareSensors,cpu_zone_temperature,short_model
from rio_monitor.windows_gpu import Adapter,aggregate_engines


class Counter:
    def read(self):return {'00000000:00000001':12.0,'00000000:00000002':76.0}
    def read_raw(self):return [(r'\_TZ.TZ00',301.0)]
    def close(self):pass
class Temperatures:
    def read(self,identifier):return None


class SensorTests(unittest.TestCase):
    def test_engines_sum_processes_but_do_not_sum_parallel_engines(self):
        def row(pid,engine,value):return (f'pid_{pid}_luid_0x00000000_0x00000001_phys_0_eng_{engine}_engtype_3D',value)
        values=aggregate_engines([row(1,0,30),row(2,0,25),row(1,1,40),row(3,1,float('nan')),('invalid',99)])
        self.assertEqual(values,{'00000000:00000001':55})
        self.assertEqual(aggregate_engines([row(1,0,120)]),{'00000000:00000001':100})
    def test_thermal_zone_requires_cpu_identity(self):
        self.assertIsNone(cpu_zone_temperature([(r'\_TZ.TZ00',301.0)]))
        self.assertAlmostEqual(cpu_zone_temperature([(r'\_TZ.CPUZ',300.15)]),27)
        self.assertIsNone(cpu_zone_temperature([('CPU',0),('CPU2',float('nan'))]))
    def test_active_gpu_does_not_rotate_with_time(self):
        clock=[10.0]
        sensors=HardwareSensors(adapters=[Adapter('00000000:00000001','Intel Graphics',0x8086),Adapter('00000000:00000002','RTX 5060',0x10de)],counters=Counter(),temperatures=Temperatures(),thermal=Counter(),clock=lambda:clock[0])
        for delta,index,usage in ((0,1,76),(4.99,1,76),(5,1,76),(9.99,1,76),(10,1,76),(25,1,76)):
            clock[0]=10+delta
            cpu,rows,selected=sensors.read()
            self.assertEqual(selected.index,index);self.assertEqual(selected.usage,usage);self.assertEqual(selected.count,2)
            self.assertIsNone(cpu)
        sensors.close()
    def test_zero_or_single_adapter(self):
        for adapters in ([],[Adapter('00000000:00000001','Intel Graphics',0x8086)]):
            sensors=HardwareSensors(adapters=adapters,counters=Counter(),temperatures=Temperatures(),thermal=Counter())
            _,rows,selected=sensors.read();self.assertEqual(len(rows),len(adapters))
            self.assertEqual(selected is None,not adapters);sensors.close()
    def test_missing_gpu_data_stays_unknown(self):
        class Missing(Counter):
            def read(self):return None
        sensors=HardwareSensors(adapters=[Adapter('00000000:00000001','GPU',0)],counters=Missing(),temperatures=Temperatures(),thermal=Counter())
        self.assertIsNone(sensors.read()[2].usage);sensors.close()
    def test_short_names_preserve_model_numbers(self):
        self.assertEqual(short_model('Intel(R) Core(TM) Ultra 9 275HX'),'Core Ultra 9 275HX')
        self.assertEqual(short_model('NVIDIA GeForce RTX 5060 Laptop GPU'),'RTX 5060')
    def test_cpu_service_reading_is_used_when_system_thermal_zone_is_anonymous(self):
        from rio_monitor.temperature_component import TemperatureComponent
        from pathlib import Path
        import time
        component=TemperatureComponent(Path(),start=False);component.value=58;component.stamp=time.monotonic()
        sensors=HardwareSensors(adapters=[],counters=Counter(),temperatures=Temperatures(),thermal=Counter(),component=component)
        self.assertEqual(sensors.read()[0],58)
        component.request(False);self.assertIsNone(sensors.read()[0]);sensors.close()


if __name__=='__main__':unittest.main()
