using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

// LibreHardwareMonitor includes distances to TjMax in SensorType.Temperature.
// Only names for actual CPU readings are eligible for the CPU gauge.
internal sealed class CpuTemperature
{
    static readonly Regex CoreOrDie = new Regex(
        @"^(?:(?:CPU )?(?:[PE]-)?Core(?: #?\d+(?:\s*-\s*#?\d+)?)?(?: \(Tdie\))?|CPU Cores|CCD\s*#?\d+(?: \(Tdie\))?)$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
    int priority = Int32.MaxValue;
    internal string Sensor { get; private set; }
    internal double? Value { get; private set; }

    // Order sensors within each physical processor before comparing sockets.
    static int Priority(string name)
    {
        switch (name.ToUpperInvariant())
        {
            case "CPU PACKAGE":
            case "CORE (TDIE)":
            case "TDIE": return 0;
            case "CORE (TCTL/TDIE)":
            case "TCTL/TDIE": return 1;
            case "CORE AVERAGE": return 2;
            case "CORE MAX": return 3;
            case "CORE (TCTL)":
            case "TCTL": return 5;
            default: return CoreOrDie.IsMatch(name) ? 4 : Int32.MaxValue;
        }
    }

    internal void Consider(string name, double value)
    {
        if (String.IsNullOrWhiteSpace(name) || !(value > 0 && value <= 125)) return;
        name = name.Trim();
        int rank = Priority(name);
        if (rank == Int32.MaxValue || rank > priority) return;
        if (rank == priority && Value.HasValue && value <= Value.Value) return;
        priority = rank;
        Sensor = name;
        Value = value;
    }

    internal static CpuTemperature HottestSocket(IEnumerable<CpuTemperature> sockets)
    {
        return sockets.Where(s => s.Value.HasValue).OrderByDescending(s => s.Value.Value).FirstOrDefault();
    }
}
