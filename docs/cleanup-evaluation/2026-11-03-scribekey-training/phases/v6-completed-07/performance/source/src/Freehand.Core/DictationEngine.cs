using System.Diagnostics;
using System.Text;
using System.Threading.Channels;
using Freehand.Abstractions;
using Freehand.Dictionary;

namespace Freehand.Core;

/// <summary>The lifecycle of one accepted recording.</summary>
public enum DictationState
{
    /// <summary>Waiting for a press.</summary>
    Idle,
    /// <summary>Capturing.</summary>
    Recording,
    /// <summary>Draining capture and waiting for loading.</summary>
    Preparing,
    /// <summary>Decoding segments.</summary>
    Transcribing,
    /// <summary>Conservatively editing the complete transcript.</summary>
    Cleaning,
    /// <summary>Restarting a failed worker.</summary>
    Recovering,
    /// <summary>Holding one failed recording.</summary>
    AwaitingRetry,
    /// <summary>Attempting delivery once.</summary>
    Delivering,
    /// <summary>Cancelling on Quit.</summary>
    Stopping,
}
/// <summary>Typed outcomes for user feedback and diagnostics.</summary>
public enum DictationOutcome
{
    /// <summary>Text produced.</summary>
    Success,
    /// <summary>Microphone or hook failed.</summary>
    CaptureFailure,
    /// <summary>Model or worker failed.</summary>
    ModelFailure,
    /// <summary>A worker deadline expired.</summary>
    Timeout,
    /// <summary>No usable audio or text.</summary>
    EmptySpeech,
    /// <summary>Shutdown cancelled work.</summary>
    Cancelled,
    /// <summary>Text remains available to copy.</summary>
    DeliveryFailure,
    /// <summary>A previous job must finish.</summary>
    Busy,
    /// <summary>Processing audio captured at the recording limit.</summary>
    RecordingLimit,
}
/// <summary>Feedback contains a user action, never native exception details.</summary>
public sealed record DictationFeedback(DictationOutcome Outcome, string Message, Guid JobId);
/// <summary>Whether optional cleanup supplied the delivered transcript.</summary>
public enum TranscriptCleanupOutcome
{
    /// <summary>No cleanup was requested for this recording.</summary>
    Disabled,
    /// <summary>Complete validated cleanup changed the transcript.</summary>
    Applied,
    /// <summary>Complete cleanup kept the transcript unchanged.</summary>
    Unchanged,
    /// <summary>The cleanup deadline expired; the original was retained.</summary>
    TimedOut,
    /// <summary>The processor failed or was still finishing an earlier job.</summary>
    Failed,
    /// <summary>The processor output failed structural or literal validation.</summary>
    Rejected,
}
/// <summary>One dictation, timed from release through delivery.</summary>
public sealed record DictationResult(DateTimeOffset At, TimeSpan AudioDuration, TimeSpan ProcessingTime,
    string Text, IReadOnlyList<AppliedCorrection> Corrections)
{
    /// <summary>Stable across transcription retries.</summary>
    public Guid JobId { get; init; }
    /// <summary>The single automatic delivery outcome.</summary>
    public DeliveryOutcome Delivery { get; init; }
    /// <summary>Release through first insertion attempt.</summary>
    public TimeSpan? FirstInsertionTime { get; init; }
    /// <summary>Release through corrected transcript readiness, before delivery.</summary>
    public TimeSpan TranscriptTime { get; init; }
    /// <summary>Dictionary-corrected, normalized text before optional cleanup.</summary>
    public string? OriginalText { get; init; }
    /// <summary>The optional cleanup outcome.</summary>
    public TranscriptCleanupOutcome CleanupOutcome { get; init; }
    /// <summary>Complete cleanup time, including failure and fallback.</summary>
    public TimeSpan CleanupTime { get; init; }
}
/// <summary>Named capture limits.</summary>
public sealed record DictationOptions
{
    /// <summary>Initial ten-minute limit.</summary>
    public TimeSpan RecordingLimit { get; init; } = TimeSpan.FromMinutes(10);
    /// <summary>Maximum progressive segment duration, from one to fifteen seconds.</summary>
    public int MaxSegmentSeconds { get; init; } = AudioSegmenter.MaxSegmentSeconds;
}
/// <summary>Owns capture, one retained recording, correction and delivery.</summary>
public sealed class DictationEngine : IAsyncDisposable
{
    private readonly IAudioCapture _capture;
    private IHotkeySource _hotkey;
    private readonly ITranscriber _speech;
    private readonly ITextInjector _injector;
    private readonly IForegroundWindow? _foreground;
    private readonly IClock _clock;
    private readonly Func<IReadOnlyList<DictionaryEntry>> _dictionary;
    private readonly Func<bool> _injectEnabled;
    private readonly DiagnosticLog? _log;
    private readonly DictationOptions _options;
    private readonly ITranscriptPostProcessor? _transcriptPostProcessor;
    private readonly TimeSpan _cleanupTimeout;
    private readonly Func<bool> _cleanupEnabled;
    private Task<string>? _cleanupPending;
    private readonly object _sync = new();
    private readonly CancellationTokenSource _lifetime = new();
    private CancellationTokenSource? _recording;
    private TaskCompletionSource? _released;
    private Task _operation = Task.CompletedTask;
    private FailedJob? _failed;
    private bool _disposed;
    private bool _configuring;
    private bool _updating;
    private long _releasedAt;
    private Guid _job;
    private DictationState _state;
    private sealed record FailedJob(Guid Id, IReadOnlyList<ReadOnlyMemory<float>> Audio, int SampleCount,
        ForegroundTarget Target, IReadOnlyList<DictionaryEntry> Entries, bool CleanupEnabled);
    /// <summary>Current dictation state.</summary>
    public DictationState State { get { lock (_sync) return _state; } }
    /// <summary>Input level.</summary>
    public float Level { get; private set; }
    /// <summary>Text retained even when persistent history is disabled.</summary>
    public DictationResult? LastResult { get; private set; }
    /// <summary>Latest feedback.</summary>
    public DictationFeedback? Feedback { get; private set; }
    /// <summary>Whether Quit would discard audio.</summary>
    public bool HasPendingAudio => State is not DictationState.Idle and not DictationState.Stopping;
    /// <summary>Fires once after the single delivery attempt.</summary>
    public event EventHandler<DictationResult>? Completed;
    /// <summary>State or level changed on a background thread.</summary>
    public event EventHandler? Changed;
    /// <summary>Connects the dictation flow to its platform interfaces.</summary>
    public DictationEngine(IAudioCapture capture, IHotkeySource hotkey, ITranscriber transcriber,
        ITextInjector injector, Func<IReadOnlyList<DictionaryEntry>> dictionary, IClock? clock = null,
        Func<bool>? injectEnabled = null, IForegroundWindow? foreground = null,
        DiagnosticLog? log = null, DictationOptions? options = null,
        ITranscriptPostProcessor? transcriptPostProcessor = null, TimeSpan? cleanupTimeout = null,
        Func<bool>? cleanupEnabled = null)
    {
        _capture = capture; _hotkey = hotkey; _speech = transcriber; _injector = injector;
        _dictionary = dictionary; _clock = clock ?? SystemClock.Instance;
        _injectEnabled = injectEnabled ?? (() => true); _foreground = foreground; _log = log;
        _options = options ?? new DictationOptions();
        _transcriptPostProcessor = transcriptPostProcessor;
        _cleanupTimeout = cleanupTimeout ?? TimeSpan.FromMinutes(2);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(_cleanupTimeout, TimeSpan.Zero, nameof(cleanupTimeout));
        _cleanupEnabled = cleanupEnabled ?? (() => true);
        ArgumentOutOfRangeException.ThrowIfLessThan(_options.MaxSegmentSeconds, 1, nameof(options));
        ArgumentOutOfRangeException.ThrowIfGreaterThan(_options.MaxSegmentSeconds, AudioSegmenter.MaxSegmentSeconds, nameof(options));
        Subscribe(_hotkey);
    }
    /// <summary>Arms the hotkey and reports startup failure.</summary>
    public bool Start()
    {
        var ready = _hotkey.Start();
        if (!ready) Report(DictationOutcome.CaptureFailure, "The dictation key could not start. Choose Retry in Freehand.");
        return ready;
    }
    /// <summary>Reinstalls a stale hook after resume or Retry.</summary>
    public bool RefreshReadiness()
    {
        lock (_sync) { if (_state != DictationState.Idle || _disposed) return false; _hotkey.StopListening(); return Start(); }
    }
    /// <summary>Applies a new hook, rolling back if it fails. Call while idle.</summary>
    public bool ReplaceHotkey(IHotkeySource replacement)
    {
        ArgumentNullException.ThrowIfNull(replacement);
        lock (_sync)
        {
            if (_state != DictationState.Idle || _disposed) { replacement.Dispose(); return false; }
            _hotkey.StopListening();
            if (!replacement.Start())
            {
                replacement.Dispose(); Start();
                Report(DictationOutcome.CaptureFailure, "That dictation key failed. The previous key was restored.");
                return false;
            }
            Unsubscribe(_hotkey); _hotkey.Dispose(); _hotkey = replacement; Subscribe(_hotkey); return true;
        }
    }
    /// <summary>Routes the Record button through the hotkey lifecycle.</summary>
    public void TogglePushToTalk() { if (State == DictationState.Recording) EndRecording(); else BeginRecording(); }
    private void Subscribe(IHotkeySource key) { key.Pressed += OnPressed; key.Released += OnReleased; }
    private void Unsubscribe(IHotkeySource key) { key.Pressed -= OnPressed; key.Released -= OnReleased; }
    private void OnPressed(object? sender, EventArgs e) => BeginRecording();
    private void OnReleased(object? sender, EventArgs e) => EndRecording();
    private void BeginRecording()
    {
        lock (_sync)
        {
            if (_disposed) return;
            if (_state != DictationState.Idle || _configuring || _updating) { Report(DictationOutcome.Busy, _failed is null ? "Finishing the previous dictation or applying settings." : "Retry or discard the previous recording first."); return; }
            _job = Guid.NewGuid(); Feedback = null;
            var target = _foreground?.Capture() ?? default;
            var recording = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            var released = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _recording = recording; _released = released; SetState(DictationState.Recording);
            var job = _job;
            var cleanupEnabled = _transcriptPostProcessor is not null && _cleanupEnabled();
            _operation = Task.Run(() => RecordAsync(job, target, recording, released, cleanupEnabled));
        }
    }
    private void EndRecording()
    {
        lock (_sync)
        {
            if (_state != DictationState.Recording) return;
            _releasedAt = Stopwatch.GetTimestamp(); SetState(DictationState.Preparing);
            _recording!.Cancel(); _released!.TrySetResult();
        }
    }
    private async Task RecordAsync(Guid job, ForegroundTarget target, CancellationTokenSource recording, TaskCompletionSource released, bool cleanupEnabled)
    {
        // The recording limit also bounds the queued and retained audio. The reader is
        // sequential because one native recognizer owns the speech worker.
        var segments = Channel.CreateUnbounded<ReadOnlyMemory<float>>(new UnboundedChannelOptions
        {
            SingleReader = true, SingleWriter = true,
        });
        var audio = new RecordingBuffer(_options.MaxSegmentSeconds, segment => segments.Writer.TryWrite(segment));
        using var decodeStop = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
        var pressAt = Stopwatch.GetTimestamp();
        var load = Task.Run(async () =>
        {
            if (_speech is ISpeechSession session) await session.BeginWorkAsync(_lifetime.Token).ConfigureAwait(false);
            return await _speech.LoadAsync(_lifetime.Token).ConfigureAwait(false);
        });
        Task<string>? transcript = null;
        try
        {
            var entries = _dictionary().ToArray();
            transcript = DecodeRecordingAsync(segments.Reader, load, entries, decodeStop.Token);
            using var limit = new CancellationTokenSource();
            var stopAtLimit = StopAtLimitAsync(limit.Token);
            try
            {
                await foreach (var chunk in _capture.CaptureAsync(recording.Token).ConfigureAwait(false))
                {
                    if (audio.Count == 0) _log?.Write(job, "first-audio", Stopwatch.GetElapsedTime(pressAt));
                    var available = (int)(_options.RecordingLimit.TotalSeconds * AudioChunk.SampleRate) - audio.Count;
                    var take = Math.Min(chunk.Samples.Length, Math.Max(0, available));
                    if (take > 0) audio.Append(chunk.Samples[..take]);
                    Level = chunk.Rms(); Changed?.Invoke(this, EventArgs.Empty);
                    if (take < chunk.Samples.Length || available == take)
                    {
                        Report(DictationOutcome.RecordingLimit, "Recording reached its limit. Finishing the captured audio.");
                        EndRecording();
                    }
                }
            }
            catch (OperationCanceledException) when (recording.IsCancellationRequested) { }
            finally { await limit.CancelAsync().ConfigureAwait(false); await stopAtLimit.ConfigureAwait(false); }
            Level = 0;
            await released.Task.WaitAsync(_lifetime.Token).ConfigureAwait(false);
            if (audio.IsSilent) { Report(DictationOutcome.EmptySpeech, "No audio was heard. Check your microphone and Windows microphone access."); return; }
            audio.Complete();
            segments.Writer.TryComplete();
            await ProcessAsync(new FailedJob(job, audio.Segments, audio.Count, target, _dictionary().ToArray(), cleanupEnabled), transcript).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { Report(DictationOutcome.Cancelled, "Dictation cancelled."); }
        catch (Exception e) { _log?.Write(job, "capture-" + e.GetType().Name); Report(DictationOutcome.CaptureFailure, "The microphone stopped. Reconnect it or open Windows microphone settings, then try again."); }
        finally
        {
            segments.Writer.TryComplete();
            await decodeStop.CancelAsync().ConfigureAwait(false);
            // Observe inference on capture failure and Quit before releasing the session.
            if (transcript is not null) { try { await transcript.ConfigureAwait(false); } catch (Exception e) { _log?.Write(job, "decode-" + e.GetType().Name); } }
            try { await load.ConfigureAwait(false); } catch (Exception e) { _log?.Write(job, "load-" + e.GetType().Name); }
            if (_speech is ISpeechSession session) session.FinishWork();
            // Clear the shared owner under the same lock used by Quit before
            // disposing it, so shutdown cannot cancel an already-disposed source.
            lock (_sync)
            {
                _recording = null; _released = null; recording.Dispose(); Level = 0;
                if (!_disposed) SetState(_failed is null ? DictationState.Idle : DictationState.AwaitingRetry);
            }
        }
    }
    private async Task<string> DecodeRecordingAsync(ChannelReader<ReadOnlyMemory<float>> segments,
        Task<bool> load, IReadOnlyList<DictionaryEntry> entries, CancellationToken cancellationToken)
    {
        if (!await load.ConfigureAwait(false)) throw new InvalidOperationException("Model unavailable");
        var bias = DictionaryCorrector.BiasPhrases(entries, _speech.SupportsBiasPhrase);
        var texts = new List<string>();
        await foreach (var segment in segments.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            var text = await _speech.TranscribeAsync(segment, bias, cancellationToken).ConfigureAwait(false);
            if (!string.IsNullOrWhiteSpace(text)) texts.Add(text.Trim());
        }
        return string.Join(' ', texts);
    }
    private async Task StopAtLimitAsync(CancellationToken token)
    {
        try { await Task.Delay(_options.RecordingLimit, token).ConfigureAwait(false); EndRecording(); Report(DictationOutcome.RecordingLimit, "Recording reached its limit. Finishing the captured audio."); }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
    }
    private async Task ProcessAsync(FailedJob job, Task<string>? initialTranscript = null)
    {
        string? raw = null;
        for (var attempt = 0; attempt < 2; attempt++)
        {
            try
            {
                if (attempt > 0) { SetState(DictationState.Recovering); if (_speech is ISpeechSession session) await session.ResetAsync(_lifetime.Token).ConfigureAwait(false); }
                if (attempt == 0 && initialTranscript is not null)
                {
                    SetState(DictationState.Transcribing);
                    raw = await initialTranscript.ConfigureAwait(false);
                    break;
                }
                var loaded = await _speech.LoadAsync(_lifetime.Token).ConfigureAwait(false);
                if (!loaded) throw new InvalidOperationException("Model unavailable");
                SetState(DictationState.Transcribing);
                var texts = new List<string>();
                var bias = DictionaryCorrector.BiasPhrases(job.Entries, _speech.SupportsBiasPhrase);
                foreach (var piece in job.Audio)
                {
                    var text = await _speech.TranscribeAsync(piece, bias, _lifetime.Token).ConfigureAwait(false);
                    if (!string.IsNullOrWhiteSpace(text)) texts.Add(text.Trim());
                }
                raw = string.Join(' ', texts); break;
            }
            catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { throw; }
            catch (Exception e)
            {
                _log?.Write(job.Id, "speech-" + e.GetType().Name);
                if (attempt == 0) continue;
                _failed = job; Report(e is TimeoutException ? DictationOutcome.Timeout : DictationOutcome.ModelFailure,
                    "Could not finish after one retry. Retry or Discard the recording. Open Settings if the model needs repair."); return;
            }
        }
        _lifetime.Token.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(raw)) { _failed = null; Report(DictationOutcome.EmptySpeech, "No speech was recognized."); return; }
        var (corrected, applied, protectedRanges) = new DictionaryCorrector(job.Entries).ApplyWithProtectedRanges(raw);
        (corrected, protectedRanges) = EnglishTextNormalizer.NormalizeWithProtectedRanges(corrected, protectedRanges, job.Entries);
        var original = job.CleanupEnabled ? corrected : null;
        var cleanupOutcome = TranscriptCleanupOutcome.Disabled;
        var cleanupTime = TimeSpan.Zero;
        if (job.CleanupEnabled)
        {
            var cleanupAt = Stopwatch.GetTimestamp();
            (corrected, cleanupOutcome) = await CleanupAsync(job.Id, corrected, protectedRanges).ConfigureAwait(false);
            cleanupTime = Stopwatch.GetElapsedTime(cleanupAt);
        }
        _lifetime.Token.ThrowIfCancellationRequested();
        var transcriptTime = Stopwatch.GetElapsedTime(_releasedAt);
        _log?.Write(job.Id, "transcript-ready", transcriptTime);
        var delivery = DeliveryOutcome.Disabled;
        var hotkeyRestored = true;
        TimeSpan? firstInsertion = null;
        SetState(DictationState.Delivering);
        if (_injectEnabled())
        {
            if (_foreground is not null && !_foreground.IsCurrent(job.Target)) delivery = DeliveryOutcome.TargetChanged;
            else
            {
                firstInsertion = Stopwatch.GetElapsedTime(_releasedAt);
                try
                {
                    _lifetime.Token.ThrowIfCancellationRequested();
                    // Separate consecutive dictations at delivery. Keep the transcript
                    // and any literal whitespace supplied by dictionary corrections intact.
                    var insertionText = corrected.Length > 0 && !char.IsWhiteSpace(corrected[^1])
                        ? corrected + " " : corrected;
                    var paused = _hotkey is ITextDeliveryHotkeySource deliveryKey
                        && await deliveryKey.TryPauseForDeliveryAsync(_lifetime.Token).ConfigureAwait(false);
                    try
                    {
                        delivery = _injector is ITargetedTextInjector targeted
                            ? await targeted.InjectAsync(insertionText, job.Target, _lifetime.Token).ConfigureAwait(false)
                            : await _injector.InjectAsync(insertionText, _lifetime.Token).ConfigureAwait(false) ? DeliveryOutcome.Delivered : DeliveryOutcome.PartialOrUncertain;
                    }
                    finally
                    {
                        // Quit disposes the hook while cancelling an in-flight insertion.
                        // Never rearm it after that ownership has ended.
                        if (paused) lock (_sync) if (!_disposed) hotkeyRestored = _hotkey.Start();
                    }
                }
                catch (OperationCanceledException) { delivery = DeliveryOutcome.Cancelled; }
                catch (Exception e) { _log?.Write(job.Id, "delivery-" + e.GetType().Name); delivery = DeliveryOutcome.PartialOrUncertain; }
            }
        }
        _failed = null;
        var result = new DictationResult(_clock.Now, TimeSpan.FromSeconds((double)job.SampleCount / AudioChunk.SampleRate), Stopwatch.GetElapsedTime(_releasedAt), corrected, applied)
            { JobId = job.Id, Delivery = delivery, FirstInsertionTime = firstInsertion, TranscriptTime = transcriptTime,
                OriginalText = original, CleanupOutcome = cleanupOutcome, CleanupTime = cleanupTime };
        LastResult = result;
        if (!hotkeyRestored) Report(DictationOutcome.CaptureFailure, "The dictation key could not start. Choose Retry in Freehand.");
        else Report(delivery is DeliveryOutcome.Delivered or DeliveryOutcome.Disabled ? DictationOutcome.Success : DictationOutcome.DeliveryFailure,
            delivery switch { DeliveryOutcome.Delivered => "Transcript sent.", DeliveryOutcome.Disabled => "Transcript ready to copy.",
                DeliveryOutcome.TargetChanged => "Focus changed. Copy the transcript to your original application.",
                _ => "Delivery may be incomplete. Check the target and copy the text. It will not be sent again automatically." });
        _log?.Write(job.Id, "finished-" + delivery, result.ProcessingTime);
        Completed?.Invoke(this, result);
    }
    private async Task<(string Text, TranscriptCleanupOutcome Outcome)> CleanupAsync(
        Guid job, string original, IReadOnlyList<CorrectionRange> protectedRanges)
    {
        if (string.IsNullOrWhiteSpace(original)) return (original, TranscriptCleanupOutcome.Unchanged);
        // A timed-out provider may ignore cancellation. Never overlap it with another job.
        if (_cleanupPending is { IsCompleted: false }) return (original, TranscriptCleanupOutcome.Failed);
        SetState(DictationState.Cleaning);
        var (input, literals, markerPrefix) = ProtectLiterals(original, protectedRanges);
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
        try
        {
            var processor = _transcriptPostProcessor!;
            var token = stop.Token;
            var operation = Task.Run(async () => await processor.ProcessAsync(input, token).ConfigureAwait(false));
            _cleanupPending = operation;
            _ = ObserveCleanupAsync(operation);
            var output = await operation.WaitAsync(_cleanupTimeout, _lifetime.Token).ConfigureAwait(false);
            _lifetime.Token.ThrowIfCancellationRequested();
            if (!TryRestoreLiterals(output, literals, markerPrefix, out var restored) || !IsUsableCleanup(original, restored))
            {
                _log?.Write(job, "cleanup-rejected");
                return (original, TranscriptCleanupOutcome.Rejected);
            }
            return (restored, restored == original ? TranscriptCleanupOutcome.Unchanged : TranscriptCleanupOutcome.Applied);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { stop.Cancel(); throw; }
        catch (TimeoutException)
        {
            stop.Cancel(); _log?.Write(job, "cleanup-timeout");
            return (original, TranscriptCleanupOutcome.TimedOut);
        }
        catch (Exception e)
        {
            stop.Cancel(); _log?.Write(job, "cleanup-" + e.GetType().Name);
            return (original, TranscriptCleanupOutcome.Failed);
        }
    }
    private static async Task ObserveCleanupAsync(Task<string> operation)
    {
        // Observe late failures without allowing their text to reach a completed job.
        try { await operation.ConfigureAwait(false); }
        catch (Exception) { }
    }
    private sealed record ProtectedLiteral(string Open, string Close, string Text);
    private static (string Text, IReadOnlyList<ProtectedLiteral> Literals, string Prefix) ProtectLiterals(
        string text, IReadOnlyList<CorrectionRange> ranges)
    {
        var prefix = "[[FREEHAND_LITERAL_" + Guid.NewGuid().ToString("N") + "_";
        var output = new StringBuilder(text.Length);
        var literals = new List<ProtectedLiteral>();
        var sourceAt = 0;
        foreach (var range in ranges)
        {
            var literal = new ProtectedLiteral(prefix + literals.Count + "_START]]", prefix + literals.Count + "_END]]",
                text.Substring(range.Start, range.Length));
            output.Append(text, sourceAt, range.Start - sourceAt);
            output.Append(literal.Open).Append(literal.Text).Append(literal.Close);
            sourceAt = range.Start + range.Length; literals.Add(literal);
        }
        output.Append(text, sourceAt, text.Length - sourceAt);
        return (output.ToString(), literals, prefix);
    }
    private static bool TryRestoreLiterals(string output, IReadOnlyList<ProtectedLiteral> literals, string prefix, out string restored)
    {
        restored = string.Empty;
        if (string.IsNullOrWhiteSpace(output)) return false;
        var result = new StringBuilder(output.Length);
        var sourceAt = 0;
        foreach (var literal in literals)
        {
            var start = output.IndexOf(literal.Open, sourceAt, StringComparison.Ordinal);
            if (start < 0 || output.IndexOf(literal.Open, StringComparison.Ordinal) != start
                || output.IndexOf(literal.Open, start + literal.Open.Length, StringComparison.Ordinal) >= 0) return false;
            var contentAt = start + literal.Open.Length;
            var end = output.IndexOf(literal.Close, contentAt, StringComparison.Ordinal);
            if (end < 0 || output.IndexOf(literal.Close, StringComparison.Ordinal) != end
                || output.IndexOf(literal.Close, end + literal.Close.Length, StringComparison.Ordinal) >= 0
                || !output.AsSpan(contentAt, end - contentAt).SequenceEqual(literal.Text)) return false;
            result.Append(output, sourceAt, start - sourceAt).Append(literal.Text);
            sourceAt = end + literal.Close.Length;
        }
        result.Append(output, sourceAt, output.Length - sourceAt);
        restored = result.ToString();
        return !restored.Contains(prefix, StringComparison.Ordinal);
    }
    private static bool IsUsableCleanup(string original, string output)
    {
        if (string.IsNullOrWhiteSpace(output) || output.Length > Math.Max(16_384L, (long)original.Length * 4 + 1024)
            || output.Any(character => char.IsControl(character) && character is not ('\r' or '\n' or '\t'))) return false;
        // Structural screening complements the provider's complete-output contract. It
        // cannot establish semantic equivalence, or replace fidelity evaluation.
        string[] framing = ["<think>", "</think>", "<|im_start|>", "<|im_end|>", "<|assistant|>", "<|endoftext|>"];
        if (framing.Any(marker => output.Contains(marker, StringComparison.OrdinalIgnoreCase)
            && !original.Contains(marker, StringComparison.OrdinalIgnoreCase))) return false;
        string[] prefaces = ["Here is the cleaned", "Here's the cleaned", "Cleaned transcript:", "Corrected transcript:", "Cleaned text:", "Rewritten transcript:"];
        var trimmed = output.TrimStart();
        return !prefaces.Any(preface => trimmed.StartsWith(preface, StringComparison.OrdinalIgnoreCase)
            && !original.TrimStart().StartsWith(preface, StringComparison.OrdinalIgnoreCase))
            && (!trimmed.StartsWith("```", StringComparison.Ordinal) || original.TrimStart().StartsWith("```", StringComparison.Ordinal));
    }
    /// <summary>Retries the retained recording with its original job ID.</summary>
    public void Retry()
    {
        lock (_sync)
        {
            if (_failed is null || _state != DictationState.AwaitingRetry || _disposed || _configuring) return;
            var job = _failed; _failed = null; _releasedAt = Stopwatch.GetTimestamp(); SetState(DictationState.Recovering);
            _operation = Task.Run(async () =>
            {
                try { if (_speech is ISpeechSession session) await session.BeginWorkAsync(_lifetime.Token).ConfigureAwait(false); await ProcessAsync(job).ConfigureAwait(false); }
                catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
                catch (Exception e) { _failed = job; _log?.Write(job.Id, "retry-" + e.GetType().Name); }
                finally { if (_speech is ISpeechSession session) session.FinishWork(); lock (_sync) if (!_disposed) SetState(_failed is null ? DictationState.Idle : DictationState.AwaitingRetry); }
            });
        }
    }
    /// <summary>Releases unresolved audio.</summary>
    public void Discard() { lock (_sync) { if (_state != DictationState.AwaitingRetry) return; _failed = null; Feedback = null; SetState(DictationState.Idle); } }
    /// <summary>Reports storage trouble independently of dictation delivery.</summary>
    public void ReportStorageProblem(string message) => Report(DictationOutcome.DeliveryFailure, message);
    /// <summary>Atomically reserves an idle engine so setup cannot race a new recording.</summary>
    public bool TryPrepareForUpdate()
    {
        lock (_sync)
        {
            if (_disposed || _configuring || _state != DictationState.Idle) return false;
            _updating = true; return true;
        }
    }
    /// <summary>Restores dictation if setup could not proceed.</summary>
    public void ResumeAfterUpdateFailure() { lock (_sync) _updating = false; Changed?.Invoke(this, EventArgs.Empty); }
    /// <summary>Reserves an idle engine while live settings and readiness are updated.</summary>
    public async Task ApplyConfigurationAsync(Func<Task> apply)
    {
        ArgumentNullException.ThrowIfNull(apply);
        lock (_sync) { if (_disposed || _configuring || _updating || _state is not (DictationState.Idle or DictationState.AwaitingRetry)) return; _configuring = true; }
        try { await apply().ConfigureAwait(false); }
        finally { lock (_sync) _configuring = false; }
    }
    private void Report(DictationOutcome outcome, string message) { Feedback = new(outcome, message, _job); Changed?.Invoke(this, EventArgs.Empty); }
    private void SetState(DictationState state)
    {
        lock (_sync) { if (_disposed && state != DictationState.Stopping) return; _state = state; }
        _log?.Write(_job, "dictation-" + state); Changed?.Invoke(this, EventArgs.Empty);
    }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        Task pending;
        lock (_sync) { if (_disposed) return; _disposed = true; Unsubscribe(_hotkey); _hotkey.Dispose(); _lifetime.Cancel(); _recording?.Cancel(); _released?.TrySetResult(); SetState(DictationState.Stopping); pending = _operation; }
        await pending.ConfigureAwait(false); _failed = null;
        try { if (_transcriptPostProcessor is not null) await _transcriptPostProcessor.DisposeAsync().ConfigureAwait(false); }
        finally { await _capture.DisposeAsync().ConfigureAwait(false); await _speech.DisposeAsync().ConfigureAwait(false); _lifetime.Dispose(); }
    }
}
