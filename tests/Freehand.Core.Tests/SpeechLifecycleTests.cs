using System.Buffers.Binary;
using System.IO.Pipes;
using System.Text.Json;
using Freehand.Abstractions;
using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class SpeechLifecycleTests
{
    [Fact]
    public async Task Dictionary_bias_reaches_the_worker_and_is_scoped_to_each_request()
    {
        var launcher = new PipeWorkerLauncher();
        await using var client = Client(launcher, inference: TimeSpan.FromSeconds(5));
        await client.BeginWorkAsync(CancellationToken.None);
        await client.LoadAsync(CancellationToken.None);
        var hints = Enumerable.Range(0, 40).Select(i => $"https://example.com/{i}")
            .Concat(["Anthropic", "Claude Code", "C++"]).ToArray();
        await client.TranscribeAsync(new float[320], hints, CancellationToken.None);
        launcher.LastBiasPhrases.ShouldBe(["Anthropic", "Claude Code"]);
        await client.TranscribeAsync(new float[320], [new string('x', 1_048_577), "", "Freehand"], CancellationToken.None);
        launcher.LastBiasPhrases.ShouldBe(["Freehand"]);
        await client.TranscribeAsync(new float[320], [], CancellationToken.None);
        launcher.LastBiasPhrases.ShouldBeEmpty();
        launcher.Launches.ShouldBe(1);
        client.FinishWork();
    }

    [Fact]
    public async Task Child_protocol_failure_does_not_escape_process_wait_or_disposal()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var pipeName = "Freehand.test.protocol." + Guid.NewGuid().ToString("N");
        using var pipe = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        var launcher = new PipeWorkerLauncher();
        await using var process = launcher.Launch(pipeName, "fixture-secret");
        await pipe.WaitForConnectionAsync(deadline.Token);
        await WorkerProtocol.ReadAsync(pipe, deadline.Token);
        await WorkerProtocol.WriteAsync(pipe, new WorkerMessage(WorkerProtocol.Version, Guid.Empty, "ack"), deadline.Token);
        // Cancellation can leave an incomplete frame. A native child exits on a protocol
        // error; waiting for it must not throw that child's managed exception in its parent.
        await pipe.WriteAsync(new byte[] { 2, 0, 0, 0, (byte)'{', (byte)'"' }, deadline.Token);
        await pipe.FlushAsync(deadline.Token);
        await process.WaitForExitAsync(deadline.Token);
        launcher.LiveWorkers.ShouldBe(0);
    }

    [Fact]
    public async Task Accepted_work_prevents_idle_unload_and_a_changed_timeout_takes_effect()
    {
        var launcher = new PipeWorkerLauncher();
        await using var client = Client(launcher);
        await client.BeginWorkAsync(CancellationToken.None);
        await client.LoadAsync(CancellationToken.None);
        await Task.Delay(80);
        client.WorkerId.ShouldNotBeNull();
        client.FinishWork();
        client.SetIdleTimeout(TimeSpan.FromMilliseconds(5));
        await LifecycleTests.WaitUntilAsync(() => client.WorkerId is null);
        launcher.Launches.ShouldBe(1);
    }

    [Fact]
    public async Task Infinite_idle_retains_the_ready_worker_until_a_finite_timeout_is_restored()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher();
        await using var client = new SpeechWorkerClient(launcher, new VerifiedAssets(), time: time);
        await client.BeginWorkAsync(CancellationToken.None);
        await client.LoadAsync(CancellationToken.None);
        var workerId = client.WorkerId;
        client.FinishWork();
        time.ActiveTimers.ShouldBe(1);

        client.SetIdleTimeout(Timeout.InfiniteTimeSpan);
        time.ActiveTimers.ShouldBe(0);
        time.Advance(TimeSpan.FromDays(2));
        client.WorkerId.ShouldBe(workerId);
        client.IsReady.ShouldBeTrue();
        await client.BeginWorkAsync(CancellationToken.None);
        (await client.TranscribeAsync(new float[320], [], CancellationToken.None)).ShouldBe("Speech.");
        client.FinishWork();
        time.ActiveTimers.ShouldBe(0);

        client.SetIdleTimeout(TimeSpan.FromMinutes(5));
        time.Advance(TimeSpan.FromMinutes(4));
        client.WorkerId.ShouldBe(workerId);
        time.Advance(TimeSpan.FromMinutes(1));
        await LifecycleTests.WaitUntilAsync(() => client.WorkerId is null);
        client.State.ShouldBe(ModelState.Unloaded);
        launcher.Launches.ShouldBe(1);
        launcher.LiveWorkers.ShouldBe(0);
    }

    [Fact]
    public async Task Finite_idle_restored_during_active_work_waits_for_work_to_finish_and_disposal_stops_residency()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher();
        await using var client = new SpeechWorkerClient(launcher, new VerifiedAssets(), time: time);
        client.SetIdleTimeout(Timeout.InfiniteTimeSpan);
        await client.BeginWorkAsync(CancellationToken.None);
        await client.LoadAsync(CancellationToken.None);
        var workerId = client.WorkerId;
        client.SetIdleTimeout(TimeSpan.FromMinutes(5));
        time.Advance(TimeSpan.FromDays(2));
        client.WorkerId.ShouldBe(workerId);
        client.IsReady.ShouldBeTrue();
        time.ActiveTimers.ShouldBe(0);
        client.FinishWork();
        time.ActiveTimers.ShouldBe(1);

        client.SetIdleTimeout(Timeout.InfiniteTimeSpan);
        await client.DisposeAsync();
        client.WorkerId.ShouldBeNull();
        launcher.LiveWorkers.ShouldBe(0);
        time.ActiveTimers.ShouldBe(0);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-2)]
    public async Task Idle_timeout_rejects_zero_and_negative_values_other_than_infinite(int milliseconds)
    {
        await using var client = Client(new PipeWorkerLauncher());
        Should.Throw<ArgumentOutOfRangeException>(() => client.SetIdleTimeout(TimeSpan.FromMilliseconds(milliseconds)));
    }

    [Fact]
    public async Task Preparation_is_opt_in_and_does_not_start_before_a_worker_is_ready()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher();
        await using var client = new SpeechWorkerClient(launcher, new VerifiedAssets(), time: time);
        await client.LoadAsync(CancellationToken.None);
        await client.BeginWorkAsync(CancellationToken.None);
        time.Advance(TimeSpan.FromDays(2));
        launcher.Preparations.ShouldBe(0);
        client.PreparationCount.ShouldBe(0);
        client.FinishWork();

        var unloadedLauncher = new PipeWorkerLauncher();
        var unloadedTime = new ManualTimeProvider();
        await using var unloaded = PreparationClient(unloadedLauncher, unloadedTime);
        await unloaded.BeginWorkAsync(CancellationToken.None);
        unloadedTime.ActiveTimers.ShouldBe(0);
        unloadedLauncher.Launches.ShouldBe(0);
        unloaded.FinishWork();
    }

    [Fact]
    public async Task Begin_work_returns_without_waiting_and_finish_drains_preparation_before_real_transcription()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher { HoldPreparation = true };
        await using var client = PreparationClient(launcher, time);
        await client.LoadAsync(CancellationToken.None);
        var workerId = client.WorkerId;
        var acceptance = client.BeginWorkAsync(CancellationToken.None);
        acceptance.IsCompletedSuccessfully.ShouldBeTrue();
        await acceptance;
        await launcher.PreparationReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        client.LastInferenceTime.ShouldBe(TimeSpan.Zero);
        client.FinishWork();
        var transcript = client.TranscribeAsync(new float[320], [], CancellationToken.None).AsTask();
        transcript.IsCompleted.ShouldBeFalse();
        launcher.AllowPreparation.TrySetResult();
        (await transcript.WaitAsync(TimeSpan.FromSeconds(2))).ShouldBe("Speech.");
        client.WorkerId.ShouldBe(workerId);
        client.IsReady.ShouldBeTrue();
        client.PreparationCount.ShouldBe(1);
        time.Advance(TimeSpan.FromDays(2));
        launcher.Preparations.ShouldBe(1);
        launcher.Launches.ShouldBe(1);
    }

    [Fact]
    public async Task Preparation_repeats_only_during_work_and_never_updates_real_inference_timing()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher();
        await using var client = PreparationClient(launcher, time);
        await client.LoadAsync(CancellationToken.None);
        await client.BeginWorkAsync(CancellationToken.None);
        await LifecycleTests.WaitUntilAsync(() => client.PreparationCount == 1 && time.ActiveTimers == 1);
        time.Advance(TimeSpan.FromMilliseconds(499));
        client.PreparationCount.ShouldBe(1);
        time.Advance(TimeSpan.FromMilliseconds(1));
        await LifecycleTests.WaitUntilAsync(() => client.PreparationCount == 2 && time.ActiveTimers == 1);
        client.LastInferenceTime.ShouldBe(TimeSpan.Zero);
        client.FinishWork();
        time.ActiveTimers.ShouldBe(0);
        time.Advance(TimeSpan.FromDays(2));
        launcher.Preparations.ShouldBe(2);
        client.IsReady.ShouldBeTrue();
    }

    [Fact]
    public async Task A_new_recording_during_preparation_drain_starts_one_replacement_loop()
    {
        var time = new ManualTimeProvider();
        var launcher = new PipeWorkerLauncher { HoldPreparation = true };
        await using var client = PreparationClient(launcher, time);
        await client.LoadAsync(CancellationToken.None);
        await client.BeginWorkAsync(CancellationToken.None);
        await launcher.PreparationReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        client.FinishWork();
        await client.BeginWorkAsync(CancellationToken.None);
        launcher.AllowPreparation.TrySetResult();
        await LifecycleTests.WaitUntilAsync(() => client.PreparationCount == 2 && time.ActiveTimers == 1);
        launcher.Preparations.ShouldBe(2);
        launcher.Launches.ShouldBe(1);
        client.FinishWork();
    }

    [Fact]
    public async Task Disposal_waits_for_inflight_preparation_then_stops_its_worker()
    {
        var launcher = new PipeWorkerLauncher { HoldPreparation = true };
        await using var client = PreparationClient(launcher, new ManualTimeProvider());
        await client.LoadAsync(CancellationToken.None);
        await client.BeginWorkAsync(CancellationToken.None);
        await launcher.PreparationReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        var disposal = client.DisposeAsync().AsTask();
        disposal.IsCompleted.ShouldBeFalse();
        launcher.AllowPreparation.TrySetResult();
        await disposal.WaitAsync(TimeSpan.FromSeconds(2));
        launcher.LiveWorkers.ShouldBe(0);
        client.WorkerId.ShouldBeNull();
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task A_hung_or_invalid_preparation_reply_stops_the_worker_without_publishing_text(bool hangs)
    {
        var launcher = new PipeWorkerLauncher { HangPreparation = hangs, PreparationReplyKind = hangs ? "prepared" : "text" };
        await using var client = PreparationClient(launcher, new ManualTimeProvider(), TimeSpan.FromMilliseconds(30));
        await client.LoadAsync(CancellationToken.None);
        await client.BeginWorkAsync(CancellationToken.None);
        await launcher.PreparationReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        await LifecycleTests.WaitUntilAsync(() => client.State == ModelState.Failed);
        launcher.LiveWorkers.ShouldBe(0);
        client.WorkerId.ShouldBeNull();
        client.PreparationCount.ShouldBe(0);
        client.LastInferenceTime.ShouldBe(TimeSpan.Zero);
        client.FinishWork();
    }

    [Fact]
    public async Task Work_accepted_during_shutdown_starts_a_replacement_after_the_old_worker_exits()
    {
        var launcher = new PipeWorkerLauncher { HoldShutdown = true };
        await using var client = Client(launcher, shutdown: TimeSpan.FromSeconds(3));
        await client.BeginWorkAsync(CancellationToken.None); await client.LoadAsync(CancellationToken.None); client.FinishWork();
        await launcher.ShutdownReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        await client.BeginWorkAsync(CancellationToken.None);
        var loading = client.LoadAsync(CancellationToken.None).AsTask();
        loading.IsCompleted.ShouldBeFalse();
        launcher.AllowShutdown.TrySetResult();
        await loading;
        launcher.Launches.ShouldBe(2); launcher.PeakWorkers.ShouldBe(1);
        await Task.Delay(60);
        client.IsReady.ShouldBeTrue();
        client.FinishWork();
    }

    [Fact]
    public async Task A_stale_reply_cannot_become_a_transcript()
    {
        var launcher = new PipeWorkerLauncher { StaleTranscript = true };
        // This checks reply identity. Leave scheduling room for instrumented CI workers;
        // the separate timeout test owns the short inference deadline.
        await using var client = Client(launcher, inference: TimeSpan.FromSeconds(5));
        await client.BeginWorkAsync(CancellationToken.None); await client.LoadAsync(CancellationToken.None);
        await Should.ThrowAsync<InvalidDataException>(async () => await client.TranscribeAsync(new float[320], [], CancellationToken.None));
        client.FinishWork();
    }

    [Fact]
    public async Task Inference_timeout_is_bounded_and_reset_terminates_an_unresponsive_worker()
    {
        var launcher = new PipeWorkerLauncher { HangInference = true };
        await using var client = Client(launcher);
        await client.BeginWorkAsync(CancellationToken.None); await client.LoadAsync(CancellationToken.None);
        await Should.ThrowAsync<TimeoutException>(async () => await client.TranscribeAsync(new float[320], [], CancellationToken.None));
        await client.ResetAsync(CancellationToken.None);
        client.WorkerId.ShouldBeNull(); launcher.LiveWorkers.ShouldBe(0); client.FinishWork();
    }

    [Fact]
    public async Task Cancelled_inference_stops_the_worker_before_the_next_recording()
    {
        var launcher = new PipeWorkerLauncher { HangInference = true };
        // This test owns cancellation; a short inference deadline can win before
        // a busy runner schedules the pipe worker to receive the request.
        await using var client = Client(launcher, inference: Timeout.InfiniteTimeSpan);
        await client.BeginWorkAsync(CancellationToken.None); await client.LoadAsync(CancellationToken.None);
        using var cancel = new CancellationTokenSource();
        var request = client.TranscribeAsync(new float[320], [], cancel.Token).AsTask();
        await launcher.InferenceReceived.Task.WaitAsync(TimeSpan.FromSeconds(2));
        await cancel.CancelAsync();
        await Should.ThrowAsync<OperationCanceledException>(() => request);
        client.WorkerId.ShouldBeNull();
        launcher.HangInference = false;
        await client.LoadAsync(CancellationToken.None);
        (await client.TranscribeAsync(new float[320], [], CancellationToken.None)).ShouldBe("Speech.");
        launcher.PeakWorkers.ShouldBe(1);
        client.FinishWork();
    }

    private static SpeechWorkerClient Client(PipeWorkerLauncher launcher, TimeSpan? shutdown = null, TimeSpan? inference = null) =>
        new(launcher, new VerifiedAssets(), new WorkerOptions
        {
            IdleTimeout = TimeSpan.FromMilliseconds(20), StartupTimeout = TimeSpan.FromSeconds(2),
            InferenceTimeout = inference ?? TimeSpan.FromMilliseconds(30), ShutdownTimeout = shutdown ?? TimeSpan.FromMilliseconds(30),
        });
    private static SpeechWorkerClient PreparationClient(PipeWorkerLauncher launcher, TimeProvider time, TimeSpan? shutdown = null) =>
        new(launcher, new VerifiedAssets(), new WorkerOptions
        {
            PrepareWhileActive = true, IdleTimeout = Timeout.InfiniteTimeSpan, StartupTimeout = TimeSpan.FromSeconds(2),
            ShutdownTimeout = shutdown ?? TimeSpan.FromSeconds(5), InferenceTimeout = TimeSpan.FromSeconds(5),
        }, time);
    private sealed class VerifiedAssets : IModelAssets
    {
        public string ResolvedDirectory => Path.GetTempPath();
        public Task<bool> VerifyAsync(CancellationToken cancellationToken, bool force = false) => Task.FromResult(true);
    }
    private sealed class ManualTimeProvider : TimeProvider
    {
        private readonly List<ManualTimer> _timers = [];
        private TimeSpan _elapsed;
        internal int ActiveTimers { get { lock (_timers) return _timers.Count; } }
        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        {
            var timer = new ManualTimer(this, callback, state);
            timer.Change(dueTime, period);
            return timer;
        }
        internal void Advance(TimeSpan elapsed)
        {
            ManualTimer[] timers;
            lock (_timers) { _elapsed += elapsed; timers = [.. _timers]; }
            foreach (var timer in timers) timer.Fire();
        }
        private sealed class ManualTimer(ManualTimeProvider owner, TimerCallback callback, object? state) : ITimer
        {
            private TimeSpan _due;
            private bool _disposed;
            public bool Change(TimeSpan dueTime, TimeSpan period)
            {
                if (period != Timeout.InfiniteTimeSpan) throw new NotSupportedException("Only one-shot timers are used by these tests.");
                lock (owner._timers)
                {
                    if (_disposed) return false;
                    owner._timers.Remove(this);
                    if (dueTime != Timeout.InfiniteTimeSpan)
                    {
                        _due = owner._elapsed + dueTime;
                        owner._timers.Add(this);
                    }
                    return true;
                }
            }
            internal void Fire()
            {
                lock (owner._timers)
                {
                    if (_disposed || _due > owner._elapsed || !owner._timers.Remove(this)) return;
                }
                callback(state);
            }
            public void Dispose() { lock (owner._timers) { _disposed = true; owner._timers.Remove(this); } }
            public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
        }
    }
    private sealed class PipeWorkerLauncher : IWorkerLauncher
    {
        internal bool HoldShutdown { get; init; }
        internal bool StaleTranscript { get; init; }
        internal bool HangInference { get; set; }
        internal bool HoldPreparation { get; init; }
        internal bool HangPreparation { get; init; }
        internal string PreparationReplyKind { get; init; } = "prepared";
        internal int Preparations;
        internal int Launches { get; private set; }
        internal int LiveWorkers;
        internal int PeakWorkers;
        internal string[] LastBiasPhrases { get; private set; } = [];
        internal TaskCompletionSource ShutdownReceived { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource InferenceReceived { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource AllowShutdown { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource PreparationReceived { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource AllowPreparation { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public IWorkerProcess Launch(string pipeName, string secret)
        {
            Launches++;
            return new PipeWorker(this, pipeName, secret, Environment.ProcessId + Launches);
        }
        private sealed class PipeWorker : IWorkerProcess
        {
            private readonly CancellationTokenSource _stop = new();
            private readonly Task _task;
            public int Id { get; }
            public bool HasExited => _task.IsCompleted;
            internal PipeWorker(PipeWorkerLauncher owner, string name, string secret, int id)
            {
                Id = id;
                owner.LiveWorkers++; owner.PeakWorkers = Math.Max(owner.PeakWorkers, owner.LiveWorkers);
                _task = Task.Run(async () =>
                {
                    try
                    {
                        using var pipe = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                        await pipe.ConnectAsync(_stop.Token);
                        await WriteAsync(pipe, Guid.Empty, "hello", secret, Id, _stop.Token);
                        using var ack = await ReadAsync(pipe, _stop.Token);
                        while (true)
                        {
                            using var request = await ReadAsync(pipe, _stop.Token);
                            var message = request.RootElement;
                            var requestId = message.GetProperty("RequestId").GetGuid();
                            var kind = message.GetProperty("Kind").GetString();
                            if (kind == "load") await WriteAsync(pipe, requestId, "ready", null, 0, _stop.Token);
                            else if (kind == "prepare")
                            {
                                Interlocked.Increment(ref owner.Preparations);
                                owner.PreparationReceived.TrySetResult();
                                if (owner.HangPreparation) await Task.Delay(Timeout.Infinite, _stop.Token);
                                if (owner.HoldPreparation) await owner.AllowPreparation.Task.WaitAsync(_stop.Token);
                                await WriteAsync(pipe, requestId, owner.PreparationReplyKind, null, 0, _stop.Token);
                            }
                            else if (kind == "transcribe")
                            {
                                owner.LastBiasPhrases = message.TryGetProperty("BiasPhrases", out var phrases) && phrases.ValueKind == JsonValueKind.Array
                                    ? phrases.EnumerateArray().Select(phrase => phrase.GetString()!).ToArray() : [];
                                var audio = new byte[message.GetProperty("SampleCount").GetInt32() * 4];
                                await pipe.ReadExactlyAsync(audio, _stop.Token);
                                owner.InferenceReceived.TrySetResult();
                                if (owner.HangInference) await Task.Delay(Timeout.Infinite, _stop.Token);
                                await WriteAsync(pipe, owner.StaleTranscript ? Guid.NewGuid() : requestId, "text", "Speech.", 0, _stop.Token);
                            }
                            else if (kind == "shutdown")
                            {
                                owner.ShutdownReceived.TrySetResult();
                                if (owner.HoldShutdown) await owner.AllowShutdown.Task.WaitAsync(_stop.Token);
                                await WriteAsync(pipe, requestId, "stopped", null, 0, _stop.Token);
                                return;
                            }
                        }
                    }
                    catch (Exception e) when (e is OperationCanceledException or IOException or JsonException) { }
                    finally { Interlocked.Decrement(ref owner.LiveWorkers); }
                });
            }
            public Task WaitForExitAsync(CancellationToken cancellationToken) => _task.WaitAsync(cancellationToken);
            public void Terminate() => _stop.Cancel();
            public async ValueTask DisposeAsync() { _stop.Cancel(); await _task; _stop.Dispose(); }
            private static async Task WriteAsync(Stream stream, Guid id, string kind, string? value, int pid, CancellationToken token)
            {
                var data = JsonSerializer.SerializeToUtf8Bytes(new { Version = WorkerProtocol.Version, RequestId = id, Kind = kind, Value = value, SampleCount = 0, ProcessId = pid });
                var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, data.Length);
                await stream.WriteAsync(header, token); await stream.WriteAsync(data, token); await stream.FlushAsync(token);
            }
            private static async Task<JsonDocument> ReadAsync(Stream stream, CancellationToken token)
            {
                var header = new byte[4]; await stream.ReadExactlyAsync(header, token);
                var bytes = new byte[BinaryPrimitives.ReadInt32LittleEndian(header)]; await stream.ReadExactlyAsync(bytes, token);
                return JsonDocument.Parse(bytes);
            }
        }
    }
}
