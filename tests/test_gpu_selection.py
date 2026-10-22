import unittest
from rio_monitor.gpu_selection import ActiveGPU
from rio_monitor.model import GPUReading

def readings(a,b):
    return (GPUReading('intel','Intel',a,None,1,0,2),GPUReading('nvidia','NVIDIA',b,None,1,1,2))

class GPUSelectionTests(unittest.TestCase):
    def test_follows_new_workload_when_previous_gpu_is_idle(self):
        selection=ActiveGPU();self.assertEqual(selection.select(readings(35,0)).identifier,'intel')
        self.assertEqual(selection.select(readings(0,72)).identifier,'nvidia')
        self.assertEqual(selection.select(readings(18,0)).identifier,'intel')
    def test_keeps_last_gpu_when_every_adapter_is_idle(self):
        selection=ActiveGPU();selection.select(readings(0,80))
        for _ in range(10):self.assertEqual(selection.select(readings(0,0)).identifier,'nvidia')
    def test_transient_other_gpu_spike_does_not_flicker(self):
        selection=ActiveGPU();selection.select(readings(40,0))
        self.assertEqual(selection.select(readings(30,60)).identifier,'intel')
        self.assertEqual(selection.select(readings(40,0)).identifier,'intel')
        self.assertEqual(selection.select(readings(20,80)).identifier,'intel')
        self.assertEqual(selection.select(readings(20,85)).identifier,'nvidia')
    def test_missing_data_and_removed_gpu_remain_recoverable(self):
        selection=ActiveGPU();selection.select(readings(0,80))
        self.assertEqual(selection.select(readings(None,None)).identifier,'nvidia')
        self.assertEqual(selection.select(readings(20,0)[:1]).identifier,'intel')
        self.assertIsNone(selection.select(()))
