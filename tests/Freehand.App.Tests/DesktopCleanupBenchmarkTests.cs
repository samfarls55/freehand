using Freehand.Abstractions;
using Freehand.App;
using Freehand.Core;
using Freehand.Cleanup;
using System.Text.Json;
using Xunit;

namespace Freehand.AppTests;

public sealed class DesktopCleanupBenchmarkTests
{
    [Fact]
    public async Task Replay_borrows_the_application_processor_and_records_real_invocations()
    {
        var application = new RecordingProcessor();
        await using (var replay = new BenchmarkCleanupProcessor(application))
        {
            Assert.Equal("Clean.", await replay.ProcessAsync("um clean", CancellationToken.None));
            Assert.Equal(1, replay.Calls);
            Assert.Equal("um clean", replay.LastInput);
            Assert.Equal("Clean.", replay.LastCandidate);
        }
        Assert.False(application.Disposed);
    }

    [Fact]
    public async Task A_failed_invocation_cannot_reuse_a_previous_candidate()
    {
        var application = new RecordingProcessor();
        await using var replay = new BenchmarkCleanupProcessor(application);
        await replay.ProcessAsync("first", CancellationToken.None);
        application.Fail = true;
        await Assert.ThrowsAsync<IOException>(async () => await replay.ProcessAsync("second", CancellationToken.None));
        Assert.Equal(2, replay.Calls);
        Assert.Equal("second", replay.LastInput);
        Assert.Null(replay.LastCandidate);
    }

    [Theory]
    [InlineData(TranscriptCleanupOutcome.Disabled)]
    [InlineData(TranscriptCleanupOutcome.Rejected)]
    [InlineData(TranscriptCleanupOutcome.Failed)]
    [InlineData(TranscriptCleanupOutcome.TimedOut)]
    public async Task Executed_fallback_and_disabled_trials_do_not_qualify(TranscriptCleanupOutcome outcome)
    {
        await using var replay = new BenchmarkCleanupProcessor(new RecordingProcessor());
        await replay.ProcessAsync("um clean", CancellationToken.None);
        var report = new BenchmarkReport { IncludeCleanup = true };
        report.RecordCleanupTrial("warm", 10, Result(outcome), replay, 0);
        Assert.NotEmpty(report.Failures);
        Assert.Equal(outcome.ToString(), Assert.Single(report.CleanupTrials).Outcome);
    }

    [Fact]
    public void Claimed_acceptance_without_provider_execution_does_not_qualify()
    {
        var report = new BenchmarkReport { IncludeCleanup = true };
        report.RecordCleanupTrial("warm", 10, Result(TranscriptCleanupOutcome.Unchanged), null, 0);
        Assert.NotEmpty(report.Failures);
        Assert.Equal(0, Assert.Single(report.CleanupTrials).ProviderCalls);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, false)]
    public void Cleanup_mode_requires_both_enabled_and_available_model(bool enabled, bool available)
    {
        var report = new DesktopDeliveryReport { IncludeCleanup = true };
        Assert.False(report.ValidateCleanupSelection(enabled, available));
        Assert.NotEmpty(report.Failures);
    }

    [Fact]
    public void Explicit_cleanup_mode_uses_requested_limits_and_keeps_cold_and_long_diagnostics_separate()
    {
        var (report, replay) = FullReplay();
        report.ValidateReplayGate(replay);
        Assert.Empty(report.Failures);
        Assert.True(report.FullCleanupQualificationRequested);
        Assert.False(report.CleanupQualificationPassed, "A synthetic gate record without sampled hardware is not a qualification pass.");
        Assert.Equal(650_000_000, report.OriginalMemoryLimitBytes);
        Assert.Equal(700, report.OriginalLatencyLimitMilliseconds);
        Assert.Equal(747_500_000, report.MemoryLimitBytes);
        Assert.Equal(805, report.LatencyLimitMilliseconds);
        Assert.Equal(15, report.RequestedTolerancePercent);
        Assert.Equal(650_000_000, new DesktopDeliveryReport().MemoryLimitBytes);
        Assert.Equal(700, new DesktopDeliveryReport().LatencyLimitMilliseconds);
    }

    [Theory]
    [InlineData("fallback")]
    [InlineData("no-execution")]
    [InlineData("warm-missing")]
    [InlineData("warm-over-limit")]
    [InlineData("configuration-missing")]
    [InlineData("actual-options-missing")]
    [InlineData("app-identity-missing")]
    [InlineData("startup-unsampled")]
    [InlineData("cleanup-orphan")]
    [InlineData("teardown-missing")]
    [InlineData("warmup-missing")]
    [InlineData("long-missing")]
    [InlineData("idle-unload-missing")]
    [InlineData("idle-receipt-missing")]
    [InlineData("cleanup-recovery-missing")]
    public void Full_cleanup_gate_rejects_missing_execution_sampling_or_diagnostics(string failure)
    {
        var (report, replay) = FullReplay();
        switch (failure)
        {
            case "fallback": replay.CleanupTrials[0] = replay.CleanupTrials[0] with { Outcome = "Failed" }; break;
            case "no-execution": replay.CleanupTrials[0] = replay.CleanupTrials[0] with { ProviderCalls = 0 }; break;
            case "warm-missing": replay.CleanupTrials.RemoveAt(0); break;
            case "warm-over-limit": replay.ReleaseToFullInputMilliseconds[^1] = 805.1; break;
            case "configuration-missing": report.CleanupConfiguration = null; break;
            case "actual-options-missing": report.CleanupConfiguration = report.CleanupConfiguration! with { ActualOptions = null }; break;
            case "app-identity-missing": report.ApplicationIdentity = null; break;
            case "startup-unsampled": report.CleanupWorkersExistedBeforeMemorySampling = true; break;
            case "cleanup-orphan": report.CleanupOrphanWorkers = 1; break;
            case "teardown-missing": report.CleanupTeardownCompleted = false; break;
            case "warmup-missing": replay.CleanupWarmups.Clear(); break;
            case "long-missing": replay.LongReleaseToFullInputMilliseconds.RemoveAt(0); break;
            case "idle-unload-missing": replay.CleanupIdleUnloadObserved = false; break;
            case "idle-receipt-missing": replay.FirstAfterCleanupIdleFullInputMilliseconds = null; break;
            case "cleanup-recovery-missing": replay.CleanupCrashRecoveryPassed = false; break;
            default: throw new ArgumentOutOfRangeException(nameof(failure));
        }
        report.ValidateReplayGate(replay);
        Assert.NotEmpty(report.Failures);
    }

    [Fact]
    public void Cleanup_memory_gate_sums_desktop_speech_cleanup_and_shared_gpu_memory()
    {
        var report = new DesktopDeliveryReport { IncludeCleanup = true };
        report.RecordMemorySample([
            Process(1, "desktop", 100_000_000, 5_000_000),
            Process(2, "speech", 300_000_000, 10_000_000),
            Process(3, "cleanup", 330_000_000, 2_500_000)], null);
        report.ValidateMemoryGate();
        Assert.Empty(report.Failures);
        Assert.Equal(747_500_000, report.PeakConservativeRamBytes);
        Assert.Equal(3, report.ProcessMemoryPeaks.Count);

        var failed = new DesktopDeliveryReport { IncludeCleanup = true };
        failed.RecordMemorySample([
            Process(1, "desktop", 100_000_000, 5_000_000),
            Process(2, "speech", 300_000_000, 10_000_000),
            Process(3, "cleanup", 330_000_001, 2_500_000)], null);
        failed.ValidateMemoryGate();
        Assert.Contains(failed.Failures, error => error.Contains("physical RAM", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Offload_qualification_requires_positive_cleanup_gpu_memory_not_only_speech_activity(bool cleanupGpu)
    {
        var (report, _) = FullReplay();
        report.RequireGpuTelemetry = true;
        report.CleanupConfiguration = report.CleanupConfiguration! with
        {
            ActualOptions = JsonSerializer.SerializeToElement(new { GpuLayers = 99 }),
        };
        report.RecordMemorySample([
            new(1, "desktop", new(100, 100), new(1, 0, 0, 0, false)),
            new(2, "speech", new(100, 100), new(2, 1000, 100, 1100, true)),
            new(3, "cleanup", new(100, 100), new(3, cleanupGpu ? 1000 : 0, 0, cleanupGpu ? 1000 : 0, true))], null);
        report.ValidateMemoryGate();
        Assert.True(report.CleanupGpuOffloadRequested);
        Assert.Equal(cleanupGpu, report.CleanupGpuMemoryObserved);
        if (cleanupGpu) Assert.Empty(report.Failures);
        else Assert.Contains(report.Failures, error => error.Contains("actual cleanup worker", StringComparison.Ordinal));
    }

    [Fact]
    public void Cleanup_tracker_preserves_platform_ownership_and_exact_process_identity()
    {
        var platform = new RecordingLauncher();
        using (var tracker = new BenchmarkCleanupWorkerLauncher(platform))
        {
            var info = new CleanupWorkerStartInfo("fixture", [], new Dictionary<string, string>());
            Assert.Same(platform.Worker, tracker.Launch(info));
            Assert.Same(info, platform.Start);
            var identity = Assert.Single(tracker.Snapshot());
            Assert.Equal(Environment.ProcessId, identity.ProcessId);
            Assert.Equal("cleanup", identity.Role);
            Assert.False(identity.HasExited);
            Assert.Equal(Environment.ProcessId, Assert.Single(tracker.LiveWorkerIds()));
        }
        Assert.False(platform.Worker.Disposed);
        Assert.False(platform.Worker.Terminated);
    }

    [Fact]
    public void Manifest_snapshot_parser_uses_the_exact_supplied_bytes()
    {
        using var files = new IdentityFiles();
        var first = File.ReadAllBytes(files.Manifest);
        files.Write("changed");
        Assert.Equal("initial", LlamaCleanupOptions.LoadManifest(files.Manifest, first).ModelId);
        Assert.Equal("changed", LlamaCleanupOptions.LoadManifest(files.Manifest).ModelId);
    }

    [Fact]
    public async Task Qualification_refuses_a_fresh_manifest_that_disagrees_with_cached_actual_options()
    {
        using var files = new IdentityFiles();
        await using var configured = files.Configured();
        using var workers = new BenchmarkCleanupWorkerLauncher(new RecordingLauncher());
        files.Write("changed");
        Assert.Throws<InvalidDataException>(() => new BenchmarkCleanupReplayContext(configured, () => true, workers));
    }

    [Fact]
    public async Task Qualification_detects_A_to_B_to_A_reload_even_when_final_options_match()
    {
        using var files = new IdentityFiles();
        await using var configured = files.Configured();
        using var workers = new BenchmarkCleanupWorkerLauncher(new RecordingLauncher());
        var context = new BenchmarkCleanupReplayContext(configured, () => true, workers);
        var original = configured.BenchmarkSnapshot();
        files.Write("changed");
        await configured.ConfigureAsync(files.DirectoryPath, enabled: true, reload: true);
        files.Write("initial");
        await configured.ConfigureAsync(files.DirectoryPath, enabled: true, reload: true);
        Assert.Equal(original.OptionsFingerprint, configured.BenchmarkSnapshot().OptionsFingerprint);
        Assert.True(configured.BenchmarkSnapshot().Epoch > original.Epoch);
        Assert.Throws<InvalidDataException>(context.ValidateConfiguration);
    }

    [Fact]
    public async Task Benchmark_owned_reset_is_the_only_accepted_configuration_epoch_transition()
    {
        using var files = new IdentityFiles();
        await using var configured = files.Configured();
        using var workers = new BenchmarkCleanupWorkerLauncher(new RecordingLauncher());
        var context = new BenchmarkCleanupReplayContext(configured, () => true, workers);
        var epoch = configured.BenchmarkSnapshot().Epoch;
        await context.ResetAsync();
        Assert.Equal(epoch + 1, configured.BenchmarkSnapshot().Epoch);
        context.ValidateConfiguration();
        await configured.ConfigureAsync(files.DirectoryPath, enabled: false);
        Assert.Throws<InvalidDataException>(context.ValidateCachedIdentity);
    }

    [Fact]
    public async Task Inference_cannot_return_a_candidate_after_configuration_drift()
    {
        using var files = new IdentityFiles();
        var application = new RecordingProcessor();
        await using var configured = files.Configured(application);
        using var workers = new BenchmarkCleanupWorkerLauncher(new RecordingLauncher());
        var context = new BenchmarkCleanupReplayContext(configured, () => true, workers);
        application.BeforeReturn = () => configured.ConfigureAsync(files.DirectoryPath, enabled: true, reload: true);
        await using var replay = new BenchmarkCleanupProcessor(configured, context);
        await Assert.ThrowsAsync<InvalidDataException>(async () => await replay.ProcessAsync("public fixture", CancellationToken.None));
        Assert.Equal(1, replay.Calls);
        Assert.Null(replay.LastCandidate);
    }

    [Fact]
    public async Task Identity_failure_still_releases_the_actual_worker_during_teardown()
    {
        using var files = new IdentityFiles();
        var application = new RecordingProcessor();
        await using var configured = files.Configured(application);
        using var workers = new BenchmarkCleanupWorkerLauncher(new RecordingLauncher());
        var context = new BenchmarkCleanupReplayContext(configured, () => true, workers);
        await configured.ProcessAsync("public fixture", CancellationToken.None);
        files.Write("changed");
        await Assert.ThrowsAsync<InvalidDataException>(async () => await context.StopAsync());
        Assert.True(application.Disposed);
    }

    [Fact]
    public async Task Complete_options_identity_includes_lookup_cache_gpu_and_artifact_controls()
    {
        using var files = new IdentityFiles();
        await using var configured = files.Configured();
        var actual = configured.BenchmarkSnapshot();
        var options = actual.Options!;
        using var snapshot = JsonDocument.Parse(BenchmarkCleanupIdentity.OptionsBytes(options));
        Assert.Equal(16, snapshot.RootElement.GetProperty("PromptLookupTokens").GetInt32());
        Assert.Equal(3, snapshot.RootElement.GetProperty("PromptLookupMatchTokens").GetInt32());
        Assert.Equal("f16", snapshot.RootElement.GetProperty("CacheTypeK").GetString());
        Assert.Equal(0, snapshot.RootElement.GetProperty("GpuLayers").GetInt32());
        Assert.True(snapshot.RootElement.TryGetProperty("Artifacts", out _));
        Assert.NotEqual(actual.OptionsFingerprint, BenchmarkCleanupIdentity.Fingerprint(options with { PromptLookupTokens = 0 }));
        Assert.NotEqual(actual.OptionsFingerprint, BenchmarkCleanupIdentity.Fingerprint(options with { CacheTypeK = "q8_0" }));
        Assert.NotEqual(actual.OptionsFingerprint, BenchmarkCleanupIdentity.Fingerprint(options with { GpuLayers = 1 }));
    }

    private static (DesktopDeliveryReport, BenchmarkReport) FullReplay()
    {
        var report = new DesktopDeliveryReport
        {
            IncludeCleanup = true, ResidentPolicy = false, CleanupTeardownCompleted = true,
            CleanupConfiguration = new("fixture", "cleanup-manifest.json", new string('a', 64), new string('b', 64),
                new string('c', 64), "Emberon2", 4, 1024, 512, 64, 32, true, false, 60000,
                1, new string('d', 64), JsonSerializer.SerializeToElement(new { ModelId = "fixture" })),
            ApplicationIdentity = new("fixture.exe", new string('e', 64), Guid.Empty.ToString("D"), null),
        };
        report.OwnedCleanupWorkers.Add(new(9876, DateTime.UnixEpoch, true) { Role = "cleanup" });
        var replay = new BenchmarkReport
        {
            IncludeCleanup = true, WorkerCrashRecoveryPassed = true, TimeoutRetentionPassed = true, UnloadCycles = 20,
            CleanupIdleUnloadObserved = true, FirstAfterCleanupIdleFullInputMilliseconds = 3000, CleanupCrashRecoveryPassed = true,
        };
        replay.ColdReleaseToFullInputMilliseconds.AddRange([2000, 2500, 3000]);
        replay.ReleaseToFullInputMilliseconds.AddRange(Enumerable.Repeat(805d, 50));
        replay.LongRecordingSeconds.AddRange([30, 60]);
        replay.LongReleaseToFullInputMilliseconds.AddRange([3000, 6000]);
        replay.CleanupWarmups.Add(new("before-warm-series", 1000, 1));
        for (var index = 0; index < 50; index++)
            replay.CleanupTrials.Add(new("warm", 10, "Unchanged", 100, 1, "Public fixture.", "Public fixture.", "Public fixture.", "Public fixture."));
        foreach (var (phase, seconds) in new[]
        {
            ("forced-fresh", 1), ("forced-fresh", 3), ("forced-fresh", 10), ("long", 30), ("long", 60),
            ("first-after-cleanup-idle", 10), ("cleanup-worker-recovery", 10), ("speech-worker-recovery", 10),
        }) replay.CleanupTrials.Add(new(phase, seconds, "Unchanged", 100, 1, "Public fixture.", "Public fixture.", "Public fixture.", "Public fixture."));
        return (report, replay);
    }

    private static DictationResult Result(TranscriptCleanupOutcome outcome) =>
        new(DateTimeOffset.UtcNow, TimeSpan.FromSeconds(10), TimeSpan.FromMilliseconds(100), "Clean.", [])
        { CleanupOutcome = outcome, CleanupTime = TimeSpan.FromMilliseconds(50), OriginalText = "um clean" };
    private static DesktopProcessMemorySample Process(int id, string role, long working, long shared) =>
        new(id, role, new(working, working), new(id, 0, shared, shared, false));

    private sealed class RecordingProcessor : ITranscriptPostProcessor
    {
        internal bool Disposed { get; private set; }
        internal bool Fail { get; set; }
        internal Func<ValueTask>? BeforeReturn { get; set; }
        public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
        {
            if (BeforeReturn is not null) await BeforeReturn();
            if (Fail) throw new IOException("Fixture failure");
            return "Clean.";
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
    private sealed class IdentityFiles : IDisposable
    {
        internal string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "cleanup-identity-" + Guid.NewGuid().ToString("N"));
        internal string Manifest => Path.Combine(DirectoryPath, "cleanup-manifest.json");
        internal IdentityFiles()
        {
            Directory.CreateDirectory(DirectoryPath);
            File.WriteAllText(Path.Combine(DirectoryPath, "runtime.exe"), "fixture runtime");
            File.WriteAllText(Path.Combine(DirectoryPath, "model.gguf"), "fixture model");
            Write("initial");
        }
        internal void Write(string id) => File.WriteAllText(Manifest, JsonSerializer.Serialize(new
        {
            runtimePath = "runtime.exe", runtimeSha256 = new string('a', 64),
            modelPath = "model.gguf", modelSha256 = new string('b', 64), modelId = id,
            promptStyle = "Emberon2", contextSize = 1024, maxOutputTokens = 512,
            promptLookupTokens = 16, promptLookupMatchTokens = 3,
        }));
        internal ConfiguredTranscriptPostProcessor Configured(RecordingProcessor? processor = null) =>
            new(DirectoryPath, new RecordingLauncher(), (_, _) => processor ?? new RecordingProcessor());
        public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
    }
    private sealed class RecordingLauncher : ICleanupWorkerLauncher
    {
        internal RecordingWorker Worker { get; } = new();
        internal CleanupWorkerStartInfo? Start { get; private set; }
        public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo) { Start = startInfo; return Worker; }
    }
    private sealed class RecordingWorker : IWorkerProcess
    {
        public int Id => Environment.ProcessId;
        public bool HasExited => false;
        internal bool Disposed { get; private set; }
        internal bool Terminated { get; private set; }
        public Task WaitForExitAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public void Terminate() => Terminated = true;
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
