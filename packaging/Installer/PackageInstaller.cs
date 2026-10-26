using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Win32;

namespace Freehand.Installer;

internal static class PackageInstaller
{
    private const string UninstallKey = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Freehand";
    private static string ShortcutPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Freehand.lnk");
    internal static async Task InstallAsync(string root, IProgress<string> progress, bool isolated = false)
    {
        var data = isolated ? Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY")
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand");
        if (string.IsNullOrWhiteSpace(data) || isolated && root.Equals(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Freehand"), StringComparison.OrdinalIgnoreCase))
            throw new IOException("Isolated verification requires a separate installation and data directory.");
        var parent = Path.GetDirectoryName(root) ?? throw new IOException("Invalid installation path");
        Directory.CreateDirectory(parent);
        var stage = Path.Combine(parent, ".Freehand-stage-" + Guid.NewGuid().ToString("N"));
        var backup = Path.Combine(parent, ".Freehand-backup-" + Guid.NewGuid().ToString("N"));
        var zipPath = Path.Combine(parent, ".Freehand-payload-" + Guid.NewGuid().ToString("N") + ".zip");
        var replaced = false;
        var verified = false;
        try
        {
            progress.Report("Extracting bundled application and speech model...");
            var installerPath = Environment.ProcessPath ?? throw new IOException("Installer path unavailable");
            var baseLength = await ExtractPayloadAsync(installerPath, zipPath).ConfigureAwait(false);
            ZipFile.ExtractToDirectory(zipPath, stage);
            progress.Report("Verifying application files and model hashes...");
            var manifest = await VerifyFilesAsync(stage).ConfigureAwait(false);
            await CopyPrefixAsync(installerPath, Path.Combine(stage, "FreehandUninstall.exe"), baseLength).ConfigureAwait(false);
            await StopApplicationAsync(root).ConfigureAwait(false);
            if (Directory.Exists(root))
            {
                var legacy = root.Equals(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Freehand"), StringComparison.OrdinalIgnoreCase)
                    && File.Exists(Path.Combine(root, "Freehand.App.exe"))
                    && FileVersionInfo.GetVersionInfo(Path.Combine(root, "Freehand.App.exe")).ProductName == "Freehand";
                if (!File.Exists(Path.Combine(root, "package-manifest.json")) && !legacy) throw new IOException("The destination is not a Freehand installation.");
                await MoveInstallationAsync(root, backup).ConfigureAwait(false);
            }
            Directory.Move(stage, root); replaced = true;
            progress.Report("Checking the installed speech worker...");
            await RunAsync(Path.Combine(root, "Freehand.App.exe"), ["--verify-model"], TimeSpan.FromSeconds(90)).ConfigureAwait(false);
            await RunAsync(Path.Combine(root, "Freehand.App.exe"), ["--selftest"], TimeSpan.FromSeconds(120)).ConfigureAwait(false);
            verified = true;
            if (!isolated)
            {
                Shortcut.Create(ShortcutPath, Path.Combine(root, "Freehand.App.exe"));
                using (var key = Registry.CurrentUser.CreateSubKey(UninstallKey))
                {
                    key.SetValue("DisplayName", "Freehand"); key.SetValue("DisplayVersion", manifest.Version);
                    key.SetValue("Publisher", "Sam"); key.SetValue("InstallLocation", root);
                    key.SetValue("DisplayIcon", Path.Combine(root, "Freehand.App.exe"));
                    key.SetValue("UninstallString", Quote(Path.Combine(root, "FreehandUninstall.exe")) + " --uninstall --directory " + Quote(root));
                    key.SetValue("QuietUninstallString", Quote(Path.Combine(root, "FreehandUninstall.exe")) + " --uninstall --quiet --directory " + Quote(root));
                    key.SetValue("NoModify", 1); key.SetValue("NoRepair", 1);
                }
                // New installations start at login; upgrades preserve an existing preference.
                var settings = Path.Combine(data, "settings.json");
                var startup = true;
                if (File.Exists(settings))
                {
                    try
                    {
                        using var document = JsonDocument.Parse(await File.ReadAllTextAsync(settings).ConfigureAwait(false));
                        if (document.RootElement.ValueKind == JsonValueKind.Object && document.RootElement.TryGetProperty("StartAtLogin", out var property)
                            && property.ValueKind is JsonValueKind.True or JsonValueKind.False) startup = property.GetBoolean();
                    }
                    catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { }
                }
                using (var key = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
                {
                    if (startup) key.SetValue("Freehand", Quote(Path.Combine(root, "Freehand.App.exe")) + " --tray");
                    else key.DeleteValue("Freehand", false);
                }
            }
            var cache = Path.Combine(data, "installer", "FreehandSetup.exe");
            Directory.CreateDirectory(Path.GetDirectoryName(cache)!);
            if (!Path.GetFullPath(installerPath).Equals(cache, StringComparison.OrdinalIgnoreCase)) File.Copy(installerPath, cache, true);
            // Cleanup cannot invalidate a verified replacement or restore a partly deleted backup.
            TryCleanup(backup, parent);
            progress.Report("Freehand is ready.");
        }
        catch
        {
            if (!verified)
            {
                if (replaced) SafeDelete(root, parent);
                if (Directory.Exists(backup)) Directory.Move(backup, root);
            }
            throw;
        }
        finally
        {
            try { File.Delete(zipPath); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
            TryCleanup(stage, parent);
        }
    }
    internal static void RestartApplication(string root)
    {
        var exe = Path.Combine(root, "Freehand.App.exe");
        if (!File.Exists(exe) || IsInstallationRunning(exe)) return;
        var start = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = root };
        Process.Start(start)?.Dispose();
    }
    private static async Task<long> ExtractPayloadAsync(string installer, string destination)
    {
        await using var source = File.OpenRead(installer);
        if (source.Length < 48) throw new InvalidDataException("Installer payload missing");
        source.Position = source.Length - 48;
        var trailer = new byte[48]; await source.ReadExactlyAsync(trailer).ConfigureAwait(false);
        if (!trailer.AsSpan(40, 8).SequenceEqual("FREEHD01"u8)) throw new InvalidDataException("Installer payload missing");
        var length = BinaryPrimitives.ReadInt64LittleEndian(trailer.AsSpan(32, 8));
        var start = source.Length - 48 - length;
        if (length < 1 || start < 1) throw new InvalidDataException("Invalid installer payload");
        source.Position = start;
        await using (var output = File.Create(destination)) await CopyBytesAsync(source, output, length).ConfigureAwait(false);
        await using var verify = File.OpenRead(destination);
        var hash = await SHA256.HashDataAsync(verify).ConfigureAwait(false);
        if (!hash.AsSpan().SequenceEqual(trailer.AsSpan(0, 32))) throw new InvalidDataException("Installer checksum failed");
        return start;
    }
    private static async Task CopyPrefixAsync(string source, string destination, long count)
    {
        await using var input = File.OpenRead(source); await using var output = File.Create(destination);
        await CopyBytesAsync(input, output, count).ConfigureAwait(false);
    }
    private static async Task CopyBytesAsync(Stream input, Stream output, long remaining)
    {
        var buffer = new byte[1024 * 1024];
        while (remaining > 0)
        {
            var read = await input.ReadAsync(buffer.AsMemory(0, (int)Math.Min(remaining, buffer.Length))).ConfigureAwait(false);
            if (read == 0) throw new EndOfStreamException();
            await output.WriteAsync(buffer.AsMemory(0, read)).ConfigureAwait(false); remaining -= read;
        }
    }
    private static async Task<PackageManifest> VerifyFilesAsync(string root)
    {
        var manifest = JsonSerializer.Deserialize(await File.ReadAllTextAsync(Path.Combine(root, "package-manifest.json")).ConfigureAwait(false),
            PackageJsonContext.Default.PackageManifest) ?? throw new InvalidDataException("Package manifest missing");
        foreach (var asset in manifest.Files)
        {
            var path = Path.GetFullPath(Path.Combine(root, asset.Path));
            if (!path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Invalid package path");
            if (new FileInfo(path).Length != asset.Size) throw new InvalidDataException("Damaged package file: " + asset.Path);
            await using var file = File.OpenRead(path);
            if (!Convert.ToHexString(await SHA256.HashDataAsync(file).ConfigureAwait(false)).Equals(asset.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Damaged package file: " + asset.Path);
        }
        return manifest;
    }
    private static async Task StopApplicationAsync(string root)
    {
        var exe = Path.Combine(root, "Freehand.App.exe");
        if (!File.Exists(exe)) return;
        if (!IsInstallationRunning(exe)) return;
        if (File.Exists(Path.Combine(root, "package-manifest.json")))
            await RunAsync(exe, ["--shutdown-for-update"], TimeSpan.FromSeconds(10)).ConfigureAwait(false);
        else
        {
            // The migrated manual build predates the shutdown command and closes with its window.
            foreach (var process in Process.GetProcessesByName("Freehand.App"))
                using (process)
                    if (IsExecutable(process, exe)) process.CloseMainWindow();
        }
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        while (true)
        {
            if (!IsInstallationRunning(exe)) return;
            await Task.Delay(100, deadline.Token).ConfigureAwait(false);
        }
    }
    private static bool IsInstallationRunning(string exe)
    {
        var running = false;
        foreach (var process in Process.GetProcessesByName("Freehand.App"))
            using (process) running |= IsExecutable(process, exe);
        return running;
    }
    private static bool IsExecutable(Process process, string exe)
    {
        try { return string.Equals(process.MainModule?.FileName, exe, StringComparison.OrdinalIgnoreCase); }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException) { return false; }
    }
    private static async Task RunAsync(string exe, string[] arguments, TimeSpan timeout)
    {
        var start = new ProcessStartInfo(exe) { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, WorkingDirectory = Path.GetTempPath() };
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new IOException("Could not start installed application");
        using var deadline = new CancellationTokenSource(timeout);
        try { await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false); }
        catch (OperationCanceledException) { if (!process.HasExited) process.Kill(true); throw new TimeoutException("Installed application did not finish verification or shutdown."); }
        if (process.ExitCode != 0) throw new IOException("Installed application verification failed.");
    }
    internal static int LaunchUninstallHelper(string root, bool quiet)
    {
        if (!quiet && MessageBox.Show("Remove Freehand? Settings, dictionary and transcript history will be preserved.", "Freehand", MessageBoxButtons.OKCancel) != DialogResult.OK) return 2;
        var folder = Path.Combine(Path.GetTempPath(), "Freehand-uninstall-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var helper = Path.Combine(folder, "FreehandUninstall.exe"); File.Copy(Environment.ProcessPath!, helper);
        var start = new ProcessStartInfo(helper) { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        foreach (var argument in new[] { "--uninstall", "--cleanup", "--quiet", "--directory", root }) start.ArgumentList.Add(argument);
        Process.Start(start)?.Dispose();
        return 0;
    }
    internal static async Task UninstallAsync(string root)
    {
        if (!File.Exists(Path.Combine(root, "package-manifest.json"))) throw new IOException("This is not a Freehand installation.");
        await StopApplicationAsync(root).ConfigureAwait(false);
        using (var key = Registry.CurrentUser.OpenSubKey(UninstallKey))
            if (!string.Equals(key?.GetValue("InstallLocation") as string, root, StringComparison.OrdinalIgnoreCase)) throw new IOException("Installation ownership could not be confirmed.");
        Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false);
        using (var startup = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run")) startup.DeleteValue("Freehand", false);
        File.Delete(ShortcutPath);
        var parent = Path.GetDirectoryName(root)!;
        await RetryFileReleaseAsync(() => SafeDelete(root, parent)).ConfigureAwait(false);
        var data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand");
        SafeDelete(Path.Combine(data, "installer"), data);
    }
    private static string Quote(string value) => "\"" + value + "\"";
    private static Task MoveInstallationAsync(string source, string destination) => RetryFileReleaseAsync(() => Directory.Move(source, destination));
    private static async Task RetryFileReleaseAsync(Action action)
    {
        // Windows can briefly retain executable mappings after process exit is signalled.
        var started = Stopwatch.GetTimestamp();
        while (true)
        {
            try { action(); return; }
            catch (IOException e) when ((e.HResult & 0xffff) is 5 or 32 or 33 && Stopwatch.GetElapsedTime(started) < TimeSpan.FromSeconds(10)) { }
            catch (UnauthorizedAccessException) when (Stopwatch.GetElapsedTime(started) < TimeSpan.FromSeconds(10)) { }
            await Task.Delay(100).ConfigureAwait(false);
        }
    }
    private static void SafeDelete(string path, string parent)
    {
        var resolved = Path.GetFullPath(path); var boundary = Path.GetFullPath(parent) + Path.DirectorySeparatorChar;
        if (!resolved.StartsWith(boundary, StringComparison.OrdinalIgnoreCase) || resolved == Path.GetPathRoot(resolved)) throw new IOException("Unsafe installation cleanup path");
        if (Directory.Exists(resolved)) Directory.Delete(resolved, true);
    }
    private static void TryCleanup(string path, string parent)
    {
        try { SafeDelete(path, parent); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}
internal sealed record PackageFile(string Path, long Size, string Sha256);
internal sealed record PackageManifest(string Version, string Build, PackageFile[] Files);
[JsonSerializable(typeof(PackageManifest))]
internal sealed partial class PackageJsonContext : JsonSerializerContext;
