using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Cryptography;
using Freehand.Abstractions;

namespace Freehand.Speech;

/// <summary>Serializes IPC and worker transitions, and stops idle model residency.</summary>
public sealed class SpeechWorkerClient : ISpeechSession
{
    private readonly Lazy<ParakeetHotwords> _hotwords = new(() => new ParakeetHotwords(
        Path.Combine(AppContext.BaseDirectory, ParakeetHotwords.VocabularyFile)));

    /// <inheritdoc />
    public bool SupportsBiasPhrase(string phrase) => _hotwords.Value.Supports(phrase);

    private readonly IWorkerLauncher _launcher;
    private readonly IModelAssets _models;
    private readonly WorkerOptions _options;
    private readonly SemaphoreSlim _gate = new(1);
    private readonly object _idleSync = new();
    private readonly TimeProvider _time;
    private NamedPipeServerStream? _pipe;
    private IWorkerProcess? _process;
    private CancellationTokenSource? _idle;
    private Task _idleTask = Task.CompletedTask;
    private TimeSpan _idleTimeout;
    private long _generation;
    private int _active;
    private bool _disposed;
    private ModelState _state;
    /// <summary>Current state, accounting for an exited worker.</summary>
    public ModelState State => _state == ModelState.Ready && _process?.HasExited != false ? ModelState.Unloaded : _state;
    /// <inheritdoc />
    public bool IsReady => State == ModelState.Ready;
    /// <summary>Worker PID for local engineering measurements.</summary>
    public int? WorkerId { get { var process = _process; return process?.HasExited == false ? process.Id : null; } }
    /// <summary>Most recent connection and loading duration.</summary>
    public TimeSpan LastLoadTime { get; private set; }
    /// <inheritdoc />
    public event EventHandler? Changed;
    /// <summary>Creates an unloaded session. No child starts here.</summary>
    public SpeechWorkerClient(IWorkerLauncher launcher, IModelAssets models, WorkerOptions? options = null, TimeProvider? time = null)
    {
        _launcher = launcher; _models = models; _options = options ?? new WorkerOptions();
        _idleTimeout = _options.IdleTimeout; _time = time ?? TimeProvider.System;
    }
    /// <inheritdoc />
    public ValueTask BeginWorkAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (_idleSync) { ObjectDisposedException.ThrowIf(_disposed, this); CancelIdle(); _active++; }
        return ValueTask.CompletedTask;
    }
    /// <inheritdoc />
    public void FinishWork()
    {
        lock (_idleSync) { if (_active > 0) _active--; if (!_disposed && _active == 0) ScheduleIdle(); }
    }
    /// <inheritdoc />
    public void SetIdleTimeout(TimeSpan timeout)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(timeout, TimeSpan.Zero);
        lock (_idleSync) { _idleTimeout = timeout; if (!_disposed && _active == 0) ScheduleIdle(); }
    }
    private void CancelIdle() { _generation++; _idle?.Cancel(); }
    private void ScheduleIdle()
    {
        CancelIdle();
        var source = new CancellationTokenSource(); _idle = source;
        var generation = _generation;
        _idleTask = IdleAsync(source, generation);
    }
    private async Task IdleAsync(CancellationTokenSource source, long generation)
    {
        try
        {
            await Task.Delay(_idleTimeout, _time, source.Token).ConfigureAwait(false);
            await _gate.WaitAsync(source.Token).ConfigureAwait(false);
            try
            {
                lock (_idleSync) { if (_disposed || _active > 0 || generation != _generation) return; }
                await StopWorkerAsync().ConfigureAwait(false);
            }
            finally { _gate.Release(); }
        }
        catch (OperationCanceledException) when (source.IsCancellationRequested) { }
        catch (Exception) { SetState(ModelState.Failed); }
        finally { lock (_idleSync) { if (ReferenceEquals(_idle, source)) _idle = null; } source.Dispose(); }
    }
    /// <inheritdoc />
    public async ValueTask<bool> LoadAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (IsReady) return true;
            await StopWorkerAsync().ConfigureAwait(false);
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(_options.StartupTimeout);
            var started = Stopwatch.GetTimestamp();
            try
            {
                if (!await _models.VerifyAsync(deadline.Token).ConfigureAwait(false)) { SetState(ModelState.Failed); return false; }
                SetState(ModelState.Starting);
                var name = "Freehand.speech." + Guid.NewGuid().ToString("N");
                var secret = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
                _pipe = new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                _process = _launcher.Launch(name, secret);
                await _pipe.WaitForConnectionAsync(deadline.Token).ConfigureAwait(false);
                var hello = await WorkerProtocol.ReadAsync(_pipe, deadline.Token).ConfigureAwait(false);
                if (hello.Kind != "hello" || hello.RequestId != Guid.Empty || hello.Value != secret || hello.ProcessId != _process.Id)
                    throw new InvalidDataException("Worker authentication failed");
                await WorkerProtocol.WriteAsync(_pipe, new WorkerMessage(WorkerProtocol.Version, Guid.Empty, "ack"), deadline.Token).ConfigureAwait(false);
                SetState(ModelState.Loading);
                var response = await RequestAsync("load", _models.ResolvedDirectory, 0, default, deadline.Token).ConfigureAwait(false);
                if (response.Kind != "ready") throw new InvalidDataException("Worker did not become ready");
                LastLoadTime = Stopwatch.GetElapsedTime(started);
                SetState(ModelState.Ready); return true;
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                await StopWorkerAsync().ConfigureAwait(false); SetState(ModelState.Failed); throw new TimeoutException("Worker startup timed out");
            }
            catch
            {
                await StopWorkerAsync().ConfigureAwait(false); SetState(ModelState.Failed); throw;
            }
        }
        finally { _gate.Release(); }
    }
    /// <inheritdoc />
    public async ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!IsReady) throw new IOException("Worker exited");
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(_options.InferenceTimeout);
            try
            {
                var phrases = biasPhrases.Where(SupportsBiasPhrase)
                    .Take(WorkerProtocol.MaxBiasPhrases).ToArray();
                var response = await RequestAsync("transcribe", null, samples.Length, samples, deadline.Token, phrases).ConfigureAwait(false);
                if (response.Kind != "text") throw new InvalidDataException("Unexpected transcription reply");
                return response.Value ?? string.Empty;
            }
            catch (OperationCanceledException)
            {
                // A cancelled pipe read can leave an obsolete reply behind. A replacement
                // worker keeps the next accepted recording from consuming that reply.
                await StopWorkerAsync().ConfigureAwait(false);
                if (cancellationToken.IsCancellationRequested) throw;
                throw new TimeoutException("Inference segment timed out");
            }
        }
        finally { _gate.Release(); }
    }
    private async Task<WorkerMessage> RequestAsync(string kind, string? value, int count, ReadOnlyMemory<float> samples, CancellationToken token,
        string[]? biasPhrases = null)
    {
        var request = new WorkerMessage(WorkerProtocol.Version, Guid.NewGuid(), kind, value, count, BiasPhrases: biasPhrases);
        var pipe = _pipe ?? throw new IOException("Worker disconnected");
        await WorkerProtocol.WriteAsync(pipe, request, token).ConfigureAwait(false);
        if (count > 0) await WorkerProtocol.WriteAudioAsync(pipe, samples, token).ConfigureAwait(false);
        var response = await WorkerProtocol.ReadAsync(pipe, token).ConfigureAwait(false);
        // A reply from any obsolete request cannot reach delivery.
        if (response.RequestId != request.RequestId) throw new InvalidDataException("Obsolete worker reply");
        if (response.Kind == "error") throw new InvalidDataException("Worker reported " + response.Value);
        return response;
    }
    /// <inheritdoc />
    public async ValueTask ResetAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try { await StopWorkerAsync().ConfigureAwait(false); }
        finally { _gate.Release(); }
    }
    private async Task StopWorkerAsync()
    {
        var process = _process;
        if (process is null) { _pipe?.Dispose(); _pipe = null; SetState(ModelState.Unloaded); return; }
        SetState(ModelState.Stopping);
        using var deadline = new CancellationTokenSource(_options.ShutdownTimeout);
        try
        {
            if (!process.HasExited && _pipe?.IsConnected == true)
            {
                var reply = await RequestAsync("shutdown", null, 0, default, deadline.Token).ConfigureAwait(false);
                if (reply.Kind != "stopped") throw new InvalidDataException("Worker shutdown not acknowledged");
                await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
            }
        }
        catch (Exception e) when (e is IOException or InvalidDataException or OperationCanceledException or InvalidOperationException) { }
        finally
        {
            if (!process.HasExited) process.Terminate();
            _pipe?.Dispose(); _pipe = null;
            _process = null;
            await process.DisposeAsync().ConfigureAwait(false);
            SetState(ModelState.Unloaded);
        }
    }
    private void SetState(ModelState state) { _state = state; Changed?.Invoke(this, EventArgs.Empty); }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        Task idle;
        lock (_idleSync) { if (_disposed) return; _disposed = true; CancelIdle(); idle = _idleTask; }
        await idle.ConfigureAwait(false);
        await _gate.WaitAsync().ConfigureAwait(false);
        try { await StopWorkerAsync().ConfigureAwait(false); }
        finally { _gate.Release(); }
    }
}
