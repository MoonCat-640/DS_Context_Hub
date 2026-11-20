using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Win32;

// Embedded in Setup and its uninstaller. This helper uses the 64-bit registry
// and preserves the original value type, unexpanded variables and empty entries.
internal static class PathEntry
{
    private const string AppKey = @"Software\MoonCat-640\DS Context Hub";
    private const string MachineEnvironment = @"SYSTEM\CurrentControlSet\Control\Session Manager\Environment";

    private static bool SameDirectory(string value, string target)
    {
        string expanded = Environment.ExpandEnvironmentVariables(value.Trim().Trim('"'));
        return String.Equals(expanded.Replace('/', '\\').TrimEnd('\\'), target,
                             StringComparison.OrdinalIgnoreCase);
    }

    private static void Update(RegistryKey environment, RegistryKey app, string directory, bool add)
    {
        object raw = environment.GetValue("Path", null, RegistryValueOptions.DoNotExpandEnvironmentNames);
        if (raw != null && !(raw is string))
            throw new InvalidDataException("Unexpected PATH registry value type.");
        RegistryValueKind kind = raw == null ? RegistryValueKind.ExpandString : environment.GetValueKind("Path");
        if (kind != RegistryValueKind.String && kind != RegistryValueKind.ExpandString)
            throw new InvalidDataException("Unexpected PATH registry value type.");

        string original = (string)raw ?? "";
        var parts = new List<string>(original.Split(';'));
        int match = parts.FindLastIndex(entry => SameDirectory(entry, directory));
        if (add)
        {
            if (match >= 0) return;
            string updated = original.Length == 0 ? directory : original + ";" + directory;
            app.SetValue("PathOriginallyAbsent", raw == null ? 1 : 0, RegistryValueKind.DWord);
            app.SetValue("PathEntry", directory, RegistryValueKind.String);
            environment.SetValue("Path", updated, kind);
            return;
        }

        if (!SameDirectory((string)app.GetValue("PathEntry", ""), directory)) return;
        if (match >= 0)
        {
            parts.RemoveAt(match);
            string updated = String.Join(";", parts);
            if (updated.Length == 0 && Convert.ToInt32(app.GetValue("PathOriginallyAbsent", 0)) == 1)
                environment.DeleteValue("Path", false);
            else
                environment.SetValue("Path", updated, kind);
        }
        app.DeleteValue("PathEntry", false);
        app.DeleteValue("PathOriginallyAbsent", false);
    }

    private static int Main(string[] args)
    {
        if (args.Length != 3 || (args[0] != "add" && args[0] != "remove") ||
            (args[1] != "CurrentUser" && args[1] != "AllUsers"))
            return 1;
        try
        {
            string directory = Path.GetFullPath(args[2]).TrimEnd('\\');
            if (directory.Contains(";")) return 1;
            bool machine = args[1] == "AllUsers";
            using (var root = RegistryKey.OpenBaseKey(machine ? RegistryHive.LocalMachine : RegistryHive.CurrentUser,
                                                       RegistryView.Registry64))
            using (var app = root.OpenSubKey(AppKey, true))
            using (var environment = root.CreateSubKey(machine ? MachineEnvironment : "Environment"))
            {
                if (app == null || !SameDirectory((string)app.GetValue("InstallLocation", ""), directory))
                    return 1;
                Update(environment, app, directory, args[0] == "add");
            }
            return 0;
        }
        catch (Exception)
        {
            // The installer reports a localized error and keeps uninstall retryable.
            return 1;
        }
    }
}
