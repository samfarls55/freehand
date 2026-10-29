using System.Diagnostics;
using System.IO.Pipes;
using Freehand.Abstractions;

namespace Freehand.Speech;

/// <summary>Internal executable mode entered before Avalonia and desktop coordination.</summary>
public static class SpeechWorker
{
    /// <summary>Runs a sequential authenticated worker; a parent handle guards native hangs.</summary>
    public static async Task<int> RunAsync(string pipeName, string secret, int parentId, long parentStartTicks)
    {
        using var parent = Process.GetProcessById(parentId);
        if (parent.StartTime.ToUniversalTime().Ticks != parentStartTicks) return 2;
        // Observe the actual process handle, avoiding PID reuse. Environment.Exit also interrupts native work.
        _ = parent.WaitForExitAsync().ContinueWith(_ => Environment.Exit(0), TaskScheduler.Default);
        using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        using var startup = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await pipe.ConnectAsync(startup.Token).ConfigureAwait(false);
        var hello = new WorkerMessage(WorkerProtocol.Version, Guid.Empty, "hello", secret, ProcessId: Environment.ProcessId);
        await WorkerProtocol.WriteAsync(pipe, hello, startup.Token).ConfigureAwait(false);
        var ack = await WorkerProtocol.ReadAsync(pipe, startup.Token).ConfigureAwait(false);
        if (ack.Kind != "ack") return 2;
        ITranscriber? transcriber = null;
        try
        {
            while (pipe.IsConnected)
            {
                var message = await WorkerProtocol.ReadAsync(pipe, CancellationToken.None).ConfigureAwait(false);
                try
                {
                    switch (message.Kind)
                    {
                        case "load":
                        {
                            if (transcriber is not null) throw new InvalidDataException("Model already loaded");
                            using var resolver = new ModelResolver(message.Value);
                            if (!await resolver.VerifyAsync(CancellationToken.None).ConfigureAwait(false)) throw new InvalidDataException("Model verification failed");
                            transcriber = ModelResolver.UsesAcceleratedModel
                                ? new GgmlTranscriber(resolver.ResolvedDirectory) : new ParakeetTranscriber(resolver.ResolvedDirectory);
                            if (!await transcriber.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new InvalidDataException("Model load failed");
                            await ReplyAsync("ready").ConfigureAwait(false);
                            break;
                        }
                        case "transcribe":
                            if (transcriber is null) throw new InvalidDataException("Model not ready");
                            var samples = await WorkerProtocol.ReadAudioAsync(pipe, message.SampleCount, CancellationToken.None).ConfigureAwait(false);
                            var text = await transcriber.TranscribeAsync(samples, message.BiasPhrases ?? [], CancellationToken.None).ConfigureAwait(false);
                            await ReplyAsync("text", text).ConfigureAwait(false);
                            break;
                        case "shutdown":
                            if (transcriber is not null) { await transcriber.DisposeAsync().ConfigureAwait(false); transcriber = null; }
                            await ReplyAsync("stopped").ConfigureAwait(false);
                            return 0;
                        default: throw new InvalidDataException("Unknown request");
                    }
                }
                catch (Exception e) { await ReplyAsync("error", e.GetType().Name).ConfigureAwait(false); }
                Task ReplyAsync(string kind, string? value = null) => WorkerProtocol.WriteAsync(pipe,
                    new WorkerMessage(WorkerProtocol.Version, message.RequestId, kind, value), CancellationToken.None);
            }
            return 0;
        }
        catch (IOException) { return 0; }
        finally { if (transcriber is not null) await transcriber.DisposeAsync().ConfigureAwait(false); }
    }
}
