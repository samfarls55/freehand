using System.Security.Cryptography;
using System.Text;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class UpdateStartupTests
{
    [Fact]
    public void Interactive_startup_detects_setup_lock_and_is_allowed_after_it_is_released()
    {
        var root = Path.Combine(Path.GetTempPath(), "freehand-lock-" + Guid.NewGuid().ToString("N"));
        var name = "Local\\FreehandSetup-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(root.ToUpperInvariant())));
        using var entered = new ManualResetEventSlim(); using var finish = new ManualResetEventSlim();
        var thread = new Thread(() =>
        {
            using var mutex = new Mutex(true, name);
            entered.Set(); finish.Wait(); mutex.ReleaseMutex();
        });
        thread.Start();
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            Assert.True(new WindowsUpdateInstaller().IsInstallationInProgress(root + Path.DirectorySeparatorChar));
        }
        finally { finish.Set(); Assert.True(thread.Join(TimeSpan.FromSeconds(5))); }
        Assert.False(new WindowsUpdateInstaller().IsInstallationInProgress(root));
    }
}
