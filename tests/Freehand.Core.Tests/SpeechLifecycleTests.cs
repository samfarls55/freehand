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
        await client.TranscribeAsync(new float[320], ["Anthropic", "Claude Code", "C++"], CancellationToken.None);
        launcher.LastBiasPhrases.ShouldBe(["Anthropic", "Claude Code", "C++"]);
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
    private sealed class VerifiedAssets : IModelAssets
    {
        public string ResolvedDirectory => Path.GetTempPath();
        public Task<bool> VerifyAsync(CancellationToken cancellationToken, bool force = false) => Task.FromResult(true);
    }
    private sealed class PipeWorkerLauncher : IWorkerLauncher
    {
        internal bool HoldShutdown { get; init; }
        internal bool StaleTranscript { get; init; }
        internal bool HangInference { get; set; }
        internal int Launches { get; private set; }
        internal int LiveWorkers;
        internal int PeakWorkers;
        internal string[] LastBiasPhrases { get; private set; } = [];
        internal TaskCompletionSource ShutdownReceived { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource InferenceReceived { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal TaskCompletionSource AllowShutdown { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
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
