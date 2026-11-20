using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Win32;

// 安装器与卸载器共用这个助手，直接读写 64 位注册表中的 PATH，保留原值类型和空条目。
internal static class PathEntry
{
    private const string AppKey = @"Software\MoonCat-640\DS Context Hub";
    private const string MachineEnvironment = @"SYSTEM\CurrentControlSet\Control\Session Manager\Environment";

    private static bool SameDirectory(string value, string target)
    {
        // 只在比较时展开环境变量、忽略大小写和末尾斜杠，写回时保留其他条目的原始拼写。
        string expanded = Environment.ExpandEnvironmentVariables(value.Trim().Trim('"'));
        return String.Equals(expanded.Replace('/', '\\').TrimEnd('\\'), target,
                             StringComparison.OrdinalIgnoreCase);
    }

    private static void Update(RegistryKey environment, RegistryKey app, string directory, bool add)
    {
        // Path 可能为 REG_SZ 或 REG_EXPAND_SZ，直接读取原值才能保留诸如 %SystemRoot% 的内容。
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
            // 原有条目属于用户，找到即返回。只有本次确实新增时才记录卸载归属。
            if (match >= 0) return;
            string updated = original.Length == 0 ? directory : original + ";" + directory;
            app.SetValue("PathOriginallyAbsent", raw == null ? 1 : 0, RegistryValueKind.DWord);
            app.SetValue("PathEntry", directory, RegistryValueKind.String);
            environment.SetValue("Path", updated, kind);
            return;
        }

        // 从当前 PATH 移除自己添加的最后一个匹配项，保留安装后由其他程序做的更改。
        if (!SameDirectory((string)app.GetValue("PathEntry", ""), directory)) return;
        if (match >= 0)
        {
            parts.RemoveAt(match);
            string updated = String.Join(";", parts);
            // 注册表值原先不存在，与值存在但为空字符串是两种状态。
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
        // 三个参数依次为操作、安装范围和目录。退出码供 NSIS 显示相应语言的错误提示。
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
                // 只接受这个安装范围内已登记的应用目录。
                if (app == null || !SameDirectory((string)app.GetValue("InstallLocation", ""), directory))
                    return 1;
                Update(environment, app, directory, args[0] == "add");
            }
            return 0;
        }
        catch (Exception)
        {
            // 让 NSIS 统一处理错误，卸载可在权限问题解决后重试。
            return 1;
        }
    }
}
