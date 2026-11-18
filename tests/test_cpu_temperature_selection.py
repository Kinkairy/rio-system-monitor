"""Compile the sensor policy on its own, without drivers or private build inputs."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'sensors' / 'CpuTemperature.cs'
CASES = r"""
using System;
class TestCpuTemperature
{
    static void Expect(CpuTemperature reading, string name, double? value)
    {
        if (reading.Sensor != name || reading.Value != value)
            throw new Exception("Expected " + name + " " + value + ", got " + reading.Sensor + " " + reading.Value);
    }

    static void Main()
    {
        var intel = new CpuTemperature();
        intel.Consider("E-Core #1 Distance to TjMax", 69);
        intel.Consider("E-Core #1", 39);
        intel.Consider("CPU Package", 47);
        intel.Consider("Core Max", 50);
        intel.Consider("Core Average", 40);
        intel.Consider("P-Core #3 Distance to TjMax", 73);
        Expect(intel, "CPU Package", 47);

        var amd = new CpuTemperature();
        amd.Consider("Core (Tctl)", 76);
        amd.Consider("CCD1 (Tdie)", 67);
        amd.Consider("Core (Tdie)", 56);
        Expect(amd, "Core (Tdie)", 56);
        Expect(CpuTemperature.HottestSocket(new[] { intel, amd }), "Core (Tdie)", 56);
        var ryzen = new CpuTemperature();
        ryzen.Consider("Core (Tctl/Tdie)", 63);
        ryzen.Consider("CCD1 (Tdie)", 72);
        Expect(ryzen, "Core (Tctl/Tdie)", 63);

        var fallback = new CpuTemperature();
        fallback.Consider("Core #1", 46);
        fallback.Consider("P-Core #3", 51);
        Expect(fallback, "P-Core #3", 51);
        fallback.Consider("Core Average", 42);
        fallback.Consider("CPU Package", Double.NaN);
        fallback.Consider("CPU Package", 130);
        Expect(fallback, "Core Average", 42);

        var missing = new CpuTemperature();
        missing.Consider("CPU Package", 0);
        missing.Consider("CPU Package", Double.PositiveInfinity);
        missing.Consider("CPU Core #1 Distance to TjMax", 75);
        missing.Consider("Thermal Margin", 80);
        missing.Consider("Core Critical", 100);
        Expect(missing, null, null);
        if (CpuTemperature.HottestSocket(new[] { missing }) != null) throw new Exception("Missing CPU");
    }
}
"""


class CpuTemperatureTests(unittest.TestCase):
    def test_selection(self):
        if os.name == 'nt':
            compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
            runner = []
            if not compiler.is_file():
                self.skipTest('.NET Framework compiler unavailable')
        else:
            compiler, mono = shutil.which('mcs'), shutil.which('mono')
            if not (compiler and mono):
                self.skipTest('Mono compiler and runtime unavailable')
            runner = [mono]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            cases = path / 'Cases.cs'
            exe = path / 'check.exe'
            cases.write_text(CASES, encoding='utf-8')
            subprocess.run([str(compiler), '-nologo', '-out:' + str(exe), str(SOURCE), str(cases)], check=True)
            subprocess.run([*runner, str(exe)], check=True)
