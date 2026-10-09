using System.Globalization;

namespace Freehand.Installer;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        var quiet = args.Contains("--quiet", StringComparer.Ordinal);
        var uninstall = args.Contains("--uninstall", StringComparer.Ordinal);
        var root = Value(args, "--directory") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Freehand");
        root = Path.GetFullPath(root);
        Directory.SetCurrentDirectory(Path.GetTempPath());
        if (uninstall && !args.Contains("--cleanup", StringComparer.Ordinal))
            return PackageInstaller.LaunchUninstallHelper(root, quiet);
        if (quiet)
        {
            try
            {
                if (uninstall) PackageInstaller.UninstallAsync(root).GetAwaiter().GetResult();
                else PackageInstaller.InstallAsync(root, new Progress<string>()).GetAwaiter().GetResult();
                return 0;
            }
            catch (Exception e)
            {
                var log = Path.Combine(Path.GetTempPath(), "Freehand-setup-error.log");
                File.WriteAllText(log, e.ToString());
                return 1;
            }
        }
        ApplicationConfiguration.Initialize();
        var action = uninstall ? "Uninstall" : "Install or repair";
        if (MessageBox.Show(action + " Freehand?\n\nFreehand will close before files change. Any active recording must be resolved or discarded. Your settings, dictionary and history will be preserved.\n\n" + root,
            "Freehand setup", MessageBoxButtons.OKCancel, MessageBoxIcon.Information) != DialogResult.OK) return 2;
        using var form = new SetupWindow(root, uninstall);
        Application.Run(form);
        return form.Result;
    }
    private static string? Value(string[] args, string option)
    {
        var index = Array.IndexOf(args, option);
        return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
    }
    private sealed class SetupWindow : Form
    {
        private readonly Label _label = new() { Dock = DockStyle.Fill, TextAlign = System.Drawing.ContentAlignment.MiddleCenter, AutoSize = false };
        internal int Result { get; private set; } = 1;
        internal SetupWindow(string root, bool uninstall)
        {
            Icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
            Text = "Freehand setup"; Width = 480; Height = 180; StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false; ControlBox = false;
            Controls.Add(_label);
            Shown += async (_, _) =>
            {
                try
                {
                    var progress = new Progress<string>(s => _label.Text = s);
                    if (uninstall) await PackageInstaller.UninstallAsync(root).ConfigureAwait(true);
                    else await Task.Run(() => PackageInstaller.InstallAsync(root, progress)).ConfigureAwait(true);
                    Result = 0;
                    MessageBox.Show(uninstall ? "Freehand was removed. Your local data was preserved." : "Freehand is installed. Open it from the Start Menu and hold Right Ctrl to dictate.",
                        "Freehand", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                catch (Exception e)
                {
                    MessageBox.Show("Setup could not finish. The previous installation was preserved where possible.\n\n" + e.Message,
                        "Freehand setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                Close();
            };
        }
    }
}
