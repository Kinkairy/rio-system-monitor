// RIO temperature component. CPU reads only; no fan controls or network listener.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Management;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;
using System.Web.Script.Serialization;
using LibreHardwareMonitor.Hardware;
using Microsoft.Win32;

internal static class Component
{
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr OpenSCManagerW(string machine, string database, uint access);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr CreateServiceW(IntPtr manager, string name, string display, uint access, uint type, uint start, uint error, string binary, string group, IntPtr tag, string dependencies, string account, string password);
    [DllImport("advapi32.dll")] static extern bool CloseServiceHandle(IntPtr handle);
    internal const string ServiceName = "RIOHardwareMonitor";
    internal const int Version = 1;
    internal static readonly string InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "RIO-Monitor", "Temperature");
    internal static readonly string DataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "RIO-Monitor");
    internal static readonly string StateDir = Path.Combine(DataDir, "State");
    internal static readonly string ControlDir = Path.Combine(DataDir, "Control");
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    internal static readonly object JsonLock = new object();
    internal static string Serialize(object value) { lock (JsonLock) return Json.Serialize(value); }
    internal static double Timestamp() { return (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds; }

    internal static void Write(string path, object value)
    {
        string tmp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        using (var stream = new FileStream(tmp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        using (var writer = new StreamWriter(stream)) writer.Write(Serialize(value));
        try { if (File.Exists(path)) File.Replace(tmp, path, null); else File.Move(tmp, path); }
        finally { if (File.Exists(tmp)) File.Delete(tmp); }
    }
    internal static bool Enabled()
    {
        try
        {
            string path = Path.Combine(ControlDir, "enabled.json");
            if (new FileInfo(path).Length > 256) return false;
            Dictionary<string, object> row;
            lock (JsonLock) row = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            return row.ContainsKey("enabled") && row["enabled"] is bool && (bool)row["enabled"];
        }
        catch { return false; }
    }
    internal static void Status(string status, double? temperature)
    {
        Write(Path.Combine(StateDir, "sensors.json"), new { version = Version, timestamp = Timestamp(), status = status, cpu_temperature = temperature, source = "LibreHardwareMonitor 0.9.6 / PawnIO" });
    }
    static bool IsAdmin() { return new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator); }
    static bool ServiceExists(string name) { using (var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + name)) return key != null; }
    static string PawnIOImagePath()
    {
        using (var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\PawnIO"))
            return key == null ? "" : Convert.ToString(key.GetValue("ImagePath", ""));
    }
    static Dictionary<string, object> Ownership()
    {
        var empty = new Dictionary<string, object>();
        try
        {
            RejectReparse(StateDir);
            if (!Directory.Exists(StateDir)) return empty;
            var owner = (SecurityIdentifier)new DirectoryInfo(StateDir).GetAccessControl().GetOwner(typeof(SecurityIdentifier));
            if (!owner.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid) && !owner.IsWellKnown(WellKnownSidType.LocalSystemSid)) return empty;
            string path = Path.Combine(StateDir, "install.json");
            if (!File.Exists(path) || new FileInfo(path).Length > 4096) return empty;
            Dictionary<string, object> row;
            lock (JsonLock) row = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            return row != null && row.ContainsKey("managed_by") && Convert.ToString(row["managed_by"]) == "RIO-Monitor" ? row : empty;
        }
        catch { return empty; }
    }
    internal static bool ShouldRemovePawnIO(bool owned, string recorded, string current)
    {
        return owned && !String.IsNullOrEmpty(recorded) && !String.IsNullOrEmpty(current) && String.Equals(recorded, current, StringComparison.OrdinalIgnoreCase);
    }
    static bool OwnedPawnIO(Dictionary<string, object> row, string current)
    {
        return row.ContainsKey("pawnio_owned") && row["pawnio_owned"] is bool && (bool)row["pawnio_owned"] &&
            row.ContainsKey("pawnio_image_path") && ShouldRemovePawnIO(true, row["pawnio_image_path"] as string, current);
    }
    static void WriteOwnership(bool pawnioOwned, bool reboot)
    {
        Write(Path.Combine(StateDir, "install.json"), new { version = Version, timestamp = Timestamp(), managed_by = "RIO-Monitor", pawnio_owned = pawnioOwned, pawnio_image_path = PawnIOImagePath(), restart_required = reboot, result = "installed" });
    }

    static int Sc(string arguments, bool required)
    {
        var si = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "sc.exe"), arguments) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        using (var p = Process.Start(si))
        {
            p.StandardOutput.ReadToEnd(); p.StandardError.ReadToEnd();
            if (!p.WaitForExit(30000)) throw new IOException("Service command timed out");
            if (required && p.ExitCode != 0) throw new IOException("Service command failed: " + p.ExitCode);
            return p.ExitCode;
        }
    }
    static void RegisterService(string executable)
    {
        IntPtr manager = OpenSCManagerW(null, null, 3);
        if (manager == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            IntPtr service = CreateServiceW(manager, ServiceName, "RIO Temperature Monitor", 0xf01ff, 0x10, 2, 1, "\"" + executable + "\" --service", null, IntPtr.Zero, null, "LocalSystem", null);
            if (service == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            CloseServiceHandle(service);
        }
        finally { CloseServiceHandle(manager); }
    }
    static void RejectReparse(string path)
    {
        for (var dir = new DirectoryInfo(path); dir != null; dir = dir.Parent)
            if (dir.Exists && (dir.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Installation path contains a reparse point");
    }
    static void SecureDirectory(string path, bool control)
    {
        RejectReparse(path);
        if (Directory.Exists(path))
        {
            var owner = (SecurityIdentifier)new DirectoryInfo(path).GetAccessControl().GetOwner(typeof(SecurityIdentifier));
            if (!owner.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid) && !owner.IsWellKnown(WellKnownSidType.LocalSystemSid)) throw new IOException("Existing component directory has an unexpected owner");
        }
        Directory.CreateDirectory(path);
        var acl = new DirectorySecurity();
        acl.SetAccessRuleProtection(true, false);
        acl.SetOwner(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null));
        var inherit = InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit;
        foreach (var sid in new[] { WellKnownSidType.LocalSystemSid, WellKnownSidType.BuiltinAdministratorsSid })
            acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid, null), FileSystemRights.FullControl, inherit, PropagationFlags.None, AccessControlType.Allow));
        acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null), control ? FileSystemRights.Modify : FileSystemRights.ReadAndExecute, inherit, PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(path).SetAccessControl(acl);
    }
    static void VerifyPayload(string source)
    {
        foreach (var row in Payload.Files)
        {
            string file = Path.Combine(source, row.Key); RejectReparse(file);
            if (!File.Exists(file)) throw new IOException("Temperature payload is incomplete");
            using (var stream = File.OpenRead(file)) using (var sha = SHA256.Create())
                if (BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant() != row.Value) throw new IOException("Temperature payload checksum failed");
        }
    }
    static int Install()
    {
        if (!IsAdmin()) return 5;
        if (!Environment.Is64BitOperatingSystem || IntPtr.Size != 8) return 50;
        string source = AppDomain.CurrentDomain.BaseDirectory;
        VerifyPayload(source);
        string targetExe = Path.Combine(InstallDir, "RIO-Temperature.exe");
        if (ServiceExists(ServiceName))
        {
            using (var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + ServiceName))
            {
                string expected = "\"" + targetExe + "\" --service";
                if (!String.Equals((string)key.GetValue("ImagePath", ""), expected, StringComparison.OrdinalIgnoreCase)) throw new IOException("Service name belongs to another installation");
            }
            using (var svc = new ServiceController(ServiceName))
                if (svc.Status != ServiceControllerStatus.Stopped) { svc.Stop(); svc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(30)); }
        }
        SecureDirectory(Path.GetDirectoryName(InstallDir), false); SecureDirectory(InstallDir, false);
        SecureDirectory(DataDir, false); SecureDirectory(StateDir, false); SecureDirectory(ControlDir, true);
        string backup = Path.Combine(InstallDir, "Recovery", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss"));
        SecureDirectory(Path.Combine(InstallDir, "Recovery"), false);
        foreach (string name in Payload.Files.Keys.Concat(new[] { "RIO-Temperature.exe" }))
        {
            string destination = Path.Combine(InstallDir, name); RejectReparse(destination);
            if (File.Exists(destination)) { SecureDirectory(backup, false); File.Move(destination, Path.Combine(backup, name)); }
            File.Copy(Path.Combine(source, name), destination, false);
            var fileAcl = new FileSecurity(); fileAcl.SetAccessRuleProtection(true, false);
            foreach (var sid in new[] { WellKnownSidType.LocalSystemSid, WellKnownSidType.BuiltinAdministratorsSid }) fileAcl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid, null), FileSystemRights.FullControl, AccessControlType.Allow));
            fileAcl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null), FileSystemRights.ReadAndExecute, AccessControlType.Allow));
            File.SetAccessControl(destination, fileAcl);
        }
        bool reboot = false;
        bool pawnioExisted = ServiceExists("PawnIO");
        bool pawnioOwned = OwnedPawnIO(Ownership(), PawnIOImagePath());
        if (!pawnioExisted)
        {
            var si = new ProcessStartInfo(Path.Combine(InstallDir, "PawnIO_setup.exe"), "-install -silent") { UseShellExecute = false, CreateNoWindow = true };
            using (var p = Process.Start(si))
            {
                if (!p.WaitForExit(180000)) throw new IOException("PawnIO installation timed out");
                reboot = p.ExitCode == 3010;
                if (p.ExitCode != 0 && !reboot) throw new IOException("PawnIO installation failed: " + p.ExitCode);
            }
        }
        if (!ServiceExists("PawnIO")) throw new IOException("PawnIO service not found after installation");
        pawnioOwned = pawnioOwned || !pawnioExisted;
        WriteOwnership(pawnioOwned, reboot);
        Write(Path.Combine(ControlDir, "enabled.json"), new { enabled = true });
        if (!ServiceExists(ServiceName)) RegisterService(targetExe);
        else Sc("config " + ServiceName + " start= auto", true);
        Sc("description " + ServiceName + " \"Read-only CPU temperature for RIO Monitor\"", true);
        Sc("failure " + ServiceName + " reset= 86400 actions= restart/5000/restart/15000/restart/60000", true);
        // Interactive users may query/start/stop only; they cannot alter service configuration.
        Sc("sdset " + ServiceName + " D:(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;LCRPWPLO;;;IU)", true);
        using (var svc = new ServiceController(ServiceName))
            if (svc.Status == ServiceControllerStatus.Stopped) { svc.Start(); svc.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(30)); }
        WriteOwnership(pawnioOwned, reboot);
        return reboot ? 3010 : 0;
    }
    static void DeleteKnownFile(string directory, string name)
    {
        RejectReparse(directory);
        string target = Path.GetFullPath(Path.Combine(directory, name));
        if (!String.Equals(Path.GetDirectoryName(target), Path.GetFullPath(directory), StringComparison.OrdinalIgnoreCase)) throw new IOException("Uninstall path is outside the component directory");
        if (File.Exists(target)) File.Delete(target);
    }
    static void DeleteEmptyDirectory(string directory)
    {
        RejectReparse(directory);
        if (Directory.Exists(directory) && !Directory.EnumerateFileSystemEntries(directory).Any()) Directory.Delete(directory, false);
    }
    static int Uninstall()
    {
        if (!IsAdmin()) return 5;
        RejectReparse(InstallDir); RejectReparse(DataDir); RejectReparse(StateDir); RejectReparse(ControlDir);
        var ownership = Ownership();
        bool removePawnIO = OwnedPawnIO(ownership, PawnIOImagePath());
        if (ServiceExists(ServiceName))
        {
            using (var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + ServiceName))
                if (!String.Equals(Convert.ToString(key.GetValue("ImagePath", "")), "\"" + Path.Combine(InstallDir, "RIO-Temperature.exe") + "\" --service", StringComparison.OrdinalIgnoreCase))
                    throw new IOException("Refusing to remove another service installation");
            using (var svc = new ServiceController(ServiceName))
                if (svc.Status != ServiceControllerStatus.Stopped) { svc.Stop(); svc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(30)); }
            Sc("delete " + ServiceName, true);
        }
        bool reboot = ServiceExists(ServiceName);
        if (removePawnIO)
        {
            string source = AppDomain.CurrentDomain.BaseDirectory;
            VerifyPayload(source);
            var si = new ProcessStartInfo(Path.Combine(source, "PawnIO_setup.exe"), "-uninstall -silent") { UseShellExecute = false, CreateNoWindow = true };
            using (var p = Process.Start(si))
            {
                if (!p.WaitForExit(180000)) throw new IOException("PawnIO removal timed out");
                reboot = reboot || p.ExitCode == 3010;
                if (p.ExitCode != 0 && p.ExitCode != 3010) throw new IOException("PawnIO removal failed: " + p.ExitCode);
            }
        }
        // Remove only active files we installed. Keep recovery material and any
        // unknown files; never recursively traverse/delete a system directory.
        foreach (string name in Payload.Files.Keys.Concat(new[] { "RIO-Temperature.exe" })) DeleteKnownFile(InstallDir, name);
        foreach (string name in new[] { "sensors.json", "install.json" }) DeleteKnownFile(StateDir, name);
        DeleteKnownFile(ControlDir, "enabled.json");
        foreach (string path in new[] { StateDir, ControlDir, DataDir, InstallDir, Path.GetDirectoryName(InstallDir) }) DeleteEmptyDirectory(path);
        return reboot ? 3010 : 0;
    }
    static object ProbeExisting()
    {
        foreach (string ns in new[] { @"root\LibreHardwareMonitor", @"root\OpenHardwareMonitor" })
        {
            try
            {
                var options = new EnumerationOptions { ReturnImmediately = false, Timeout = TimeSpan.FromSeconds(2) };
                var scope = new ManagementScope(ns); scope.Options.Timeout = TimeSpan.FromSeconds(2);
                var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                using (var search = new ManagementObjectSearcher(scope, new ObjectQuery("SELECT Identifier, HardwareType FROM Hardware"), options))
                using (var rows = search.Get())
                    foreach (ManagementObject row in rows) if (String.Equals(Convert.ToString(row["HardwareType"]), "Cpu", StringComparison.OrdinalIgnoreCase)) ids.Add(Convert.ToString(row["Identifier"]));
                double? best = null;
                using (var search = new ManagementObjectSearcher(scope, new ObjectQuery("SELECT Parent, SensorType, Value FROM Sensor"), options))
                using (var rows = search.Get())
                    foreach (ManagementObject row in rows)
                    {
                        if (!String.Equals(Convert.ToString(row["SensorType"]), "Temperature", StringComparison.OrdinalIgnoreCase)) continue;
                        string parent = Convert.ToString(row["Parent"]);
                        if (!ids.Any(id => parent == id || parent.StartsWith(id + "/", StringComparison.OrdinalIgnoreCase))) continue;
                        if (row["Value"] == null) continue;
                        double value = Convert.ToDouble(row["Value"], CultureInfo.InvariantCulture);
                        if (!Double.IsNaN(value) && value > 0 && value <= 125) best = best.HasValue ? Math.Max(best.Value, value) : value;
                    }
                if (best.HasValue) return new { cpu_temperature = best, source = ns, timestamp = Timestamp() };
            }
            catch (ManagementException) { } catch (UnauthorizedAccessException) { } catch (System.Runtime.InteropServices.COMException) { }
        }
        return new { cpu_temperature = (double?)null, source = "unavailable", timestamp = Timestamp() };
    }
    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--probe-existing") { Console.WriteLine(Serialize(ProbeExisting())); return 0; }
            if (args.Length == 1 && args[0] == "--install") return Install();
            if (args.Length == 1 && args[0] == "--uninstall") return Uninstall();
            if (args.Length == 1 && args[0] == "--self-test")
            {
                bool policy = !ShouldRemovePawnIO(false, "same", "same") && !ShouldRemovePawnIO(true, "", "same") && !ShouldRemovePawnIO(true, "old", "different") && ShouldRemovePawnIO(true, "Same", "same");
                Console.WriteLine(Serialize(new { version = Version, payload_files = Payload.Files.Count, cpu_only = true, install_dir = InstallDir, uninstall_supported = true, uninstall_ownership_policy = policy })); return policy ? 0 : 1;
            }
            if (args.Length == 1 && args[0] == "--service") { ServiceBase.Run(new TemperatureService()); return 0; }
            return 87;
        }
        catch { return 1; }
    }
}

internal sealed class CpuReader : IDisposable
{
    readonly Computer computer = new Computer { IsCpuEnabled = true };
    internal CpuReader() { computer.Open(); }
    internal double? Read()
    {
        double? best = null;
        foreach (IHardware cpu in computer.Hardware)
        {
            if (cpu.HardwareType != HardwareType.Cpu) continue;
            cpu.Update();
            foreach (ISensor sensor in cpu.Sensors)
                if (sensor.SensorType == SensorType.Temperature && sensor.Value.HasValue)
                {
                    double value = sensor.Value.Value;
                    if (!Double.IsNaN(value) && value > 0 && value <= 125) best = best.HasValue ? Math.Max(best.Value, value) : value;
                }
        }
        return best;
    }
    public void Dispose() { computer.Close(); }
}

internal sealed class TemperatureService : ServiceBase
{
    readonly ManualResetEvent stop = new ManualResetEvent(false);
    Thread worker;
    internal TemperatureService() { ServiceName = Component.ServiceName; CanStop = true; CanShutdown = true; AutoLog = false; }
    protected override void OnStart(string[] args) { worker = new Thread(Run) { IsBackground = true }; worker.Start(); }
    protected override void OnStop() { stop.Set(); if (worker != null && !worker.Join(15000)) throw new IOException("Sensor shutdown timed out"); }
    protected override void OnShutdown() { OnStop(); }
    void Run()
    {
        CpuReader reader = null;
        try
        {
            while (!stop.WaitOne(0))
            {
                try
                {
                    if (!Component.Enabled())
                    {
                        if (reader != null) { reader.Dispose(); reader = null; }
                        Component.Status("disabled", null);
                    }
                    else
                    {
                        if (reader == null) reader = new CpuReader();
                        double? value = reader.Read(); Component.Status(value.HasValue ? "ready" : "unsupported", value);
                    }
                }
                catch
                {
                    if (reader != null) { try { reader.Dispose(); } catch { } reader = null; }
                    try { Component.Status("error", null); } catch { }
                    if (stop.WaitOne(4000)) break;
                }
                stop.WaitOne(1000);
            }
        }
        finally { if (reader != null) reader.Dispose(); try { Component.Status("stopped", null); } catch { } }
    }
}
