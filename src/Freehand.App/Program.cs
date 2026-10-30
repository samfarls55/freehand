using Avalonia;
using System.Diagnostics;
using System.Globalization;
using Freehand.Abstractions;
using Freehand.Speech;

namespace Freehand.App;

/// <summary>Entry point.</summary>
public static class Program
{
    internal static long LaunchedAt { get; } = Stopwatch.GetTimestamp();
    internal static IDesktopIntegration? Desktop { get; private set; }
    /// <summary>Starts the app, or runs a headless self-test.</summary>
    /// <param name="args">Command line. <c>--selftest</c> exits without showing UI.</param>
    /// <returns>0 on success.</returns>
    [STAThread]
    public static int Main(string[] args)
    {
        PlatformFactory.InstallResolver();
        if (args.Contains("--desktop-delivery-benchmark", StringComparer.Ordinal)
            && string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY")))
        {
            Console.Error.WriteLine("Desktop delivery measurement requires an isolated data directory.");
            return 1;
        }
        if (args.Length == 2 && args[0] == "--performance-check")
            return PerformanceChecks.RunAsync(args[1]).GetAwaiter().GetResult();
        if (args.Contains("--desktop-selftest", StringComparer.Ordinal))
            return EngineeringChecks.CheckDesktopAsync().GetAwaiter().GetResult();
        if (args.Length == 2 && args[0] == "--benchmark")
            return EngineeringChecks.BenchmarkAsync(args[1]).GetAwaiter().GetResult();
        if (args.Length == 5 && args[0] == "--speech-worker")
            return SpeechWorker.RunAsync(args[1], args[2], int.Parse(args[3], CultureInfo.InvariantCulture),
                long.Parse(args[4], CultureInfo.InvariantCulture)).GetAwaiter().GetResult();
        if (args.Contains("--verify-model", StringComparer.Ordinal))
        {
            using var models = new ModelResolver();
            return models.VerifyAsync(CancellationToken.None, force: true).GetAwaiter().GetResult() ? 0 : 1;
        }

        if (args.Contains("--audio-selftest", StringComparer.OrdinalIgnoreCase))
            return SelfTest.CheckAudio();

        // The published single-file exe is the only artifact CI can run end to end, and a
        // GitHub runner cannot show a window. This branch exercises startup — assembly
        // loading, native library resolution out of the self-extracted bundle, model
        // discovery — and exits, which is the class of failure that only appears after
        // publishing.
        if (args.Contains("--selftest", StringComparer.OrdinalIgnoreCase))
        {
            return SelfTest.Run();
        }

        using var desktop = PlatformFactory.CreateDesktopIntegration();
        if (args.Contains("--shutdown-for-update", StringComparer.Ordinal)) { desktop?.RequestExistingShutdown(); return 0; }
        if (PlatformFactory.CreateUpdateInstaller()?.IsInstallationInProgress(AppContext.BaseDirectory) == true) return 0;
        if (desktop is not null && !desktop.ClaimInstance()) return 0;
        Desktop = desktop;
        if (Environment.GetEnvironmentVariable("FREEHAND_UPDATE_HANDOFF_TEST") == "1")
            return UpdateHandoffProbe.RunAsync(desktop).GetAwaiter().GetResult();
        return BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
    }

    /// <summary>Configures Avalonia. Also used by the headless test host.</summary>
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            .UsePlatformDetect()
            // The Compact interface avoids a persistent Windows GPU context.
            .With(new Win32PlatformOptions { RenderingMode = [Win32RenderingMode.Software] })
            .WithInterFont()
            .LogToTrace();
}
