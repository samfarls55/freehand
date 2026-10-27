using System.Runtime.InteropServices;
using Freehand.Abstractions;
using SherpaOnnx;

namespace Freehand.Speech;

/// <summary>
/// NVIDIA Parakeet TDT 110M, running locally through sherpa-onnx.
/// </summary>
/// <remarks>
/// <para>
/// Windows has no counterpart to Apple's <c>SpeechAnalyzer</c>, so unlike the macOS build —
/// where Parakeet is an optional upgrade — this is the only engine, and the app cannot
/// transcribe until the model files are downloaded. See <c>docs/PARAKEET-WINDOWS.md</c>.
/// </para>
/// <para>
/// The pinned Windows runtime uses CPU inference on four threads. The model manifest
/// defines the encoder's feature dimension and verified assets.
/// </para>
/// <para>
/// Dictionary terms and replacement spellings bias each recognition stream.
/// Literal dictionary corrections still run after recognition.
/// </para>
/// </remarks>
public sealed class ParakeetTranscriber : ITranscriber
{
    /// <summary>CPU inference threads.</summary>
    private const int Threads = 4;

    /// <summary>
    /// Model family. <b>Required.</b> Without it the model fails to load.
    /// </summary>
    private const string ModelType = "nemo_transducer";

    private readonly string _modelDirectory;
    private ParakeetRecognizer? _recognizer;
    private ParakeetHotwords? _hotwords;

    /// <summary>Points the engine at a folder of model files.</summary>
    /// <param name="modelDirectory">
    /// Must contain <c>encoder.int8.onnx</c>, <c>decoder.int8.onnx</c>,
    /// <c>joiner.int8.onnx</c> and <c>tokens.txt</c>.
    /// </param>
    public ParakeetTranscriber(string modelDirectory) => _modelDirectory = modelDirectory;

    /// <summary>Where the model is looked for, in order.</summary>
    /// <remarks>
    /// <c>%LOCALAPPDATA%</c> first: it needs no administrator rights, so the app can download
    /// and update the model itself even when installed under Program Files.
    /// </remarks>
    public static IEnumerable<string> DefaultSearchPaths()
    {
        yield return Path.Combine(AppContext.BaseDirectory, "models", ModelResolver.DirectoryName);
        yield return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Freehand", "models", ModelResolver.DirectoryName);

        // AppContext.BaseDirectory, not Assembly.Location — the latter returns an empty
        // string in a single-file app, which silently resolves paths against the current
        // directory instead.
    }

    /// <summary>Finds a directory containing a complete model, or null.</summary>
    public static string? Locate() => DefaultSearchPaths().FirstOrDefault(IsComplete);

    /// <summary>Whether <paramref name="directory"/> holds every required file.</summary>
    /// <remarks>
    /// Worth checking before loading: a truncated download fails with an opaque protobuf
    /// parse error that reads like a corrupt build rather than a missing byte range.
    /// </remarks>
    public static bool IsComplete(string directory) =>
        RequiredFiles.All(f => File.Exists(Path.Combine(directory, f)));

    /// <summary>The files the engine needs.</summary>
    public static IReadOnlyList<string> RequiredFiles { get; } =
    [
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        "tokens.txt",
    ];

    /// <inheritdoc />
    public bool IsReady => _recognizer is not null;

    /// <inheritdoc />
    public ValueTask<bool> LoadAsync(CancellationToken cancellationToken)
    {
        if (_recognizer is not null) return ValueTask.FromResult(true);
        if (!IsComplete(_modelDirectory)) return ValueTask.FromResult(false);

        var config = new OfflineRecognizerConfig();
        config.FeatConfig.SampleRate = AudioChunk.SampleRate;
        config.FeatConfig.FeatureDim = ModelResolver.FeatureDimension;

        config.ModelConfig.Transducer.Encoder = Path.Combine(_modelDirectory, "encoder.int8.onnx");
        config.ModelConfig.Transducer.Decoder = Path.Combine(_modelDirectory, "decoder.int8.onnx");
        config.ModelConfig.Transducer.Joiner = Path.Combine(_modelDirectory, "joiner.int8.onnx");
        config.ModelConfig.Tokens = Path.Combine(_modelDirectory, "tokens.txt");
        config.ModelConfig.ModelType = ModelType;
        config.ModelConfig.NumThreads = Threads;
        config.ModelConfig.Provider = "cpu:" + Path.Combine(AppContext.BaseDirectory, "speech-cpu.config");
        // Two paths reduced word errors in the public speech comparison. Wider searches
        // added decoding time without reducing errors further.
        config.DecodingMethod = "modified_beam_search";
        config.MaxActivePaths = 2;
        config.ModelConfig.ModelingUnit = "bpe";
        config.ModelConfig.BpeVocab = Path.Combine(AppContext.BaseDirectory, ParakeetHotwords.VocabularyFile);
        _hotwords = new ParakeetHotwords(config.ModelConfig.BpeVocab);

        _recognizer = new ParakeetRecognizer(config);
        return ValueTask.FromResult(true);
    }

    /// <inheritdoc />
    public bool SupportsBiasPhrase(string phrase) => _hotwords?.Supports(phrase) == true;

    /// <inheritdoc />
    /// <remarks>
    /// Audio longer than the encoder can handle is the caller's problem; <c>AudioSegmenter</c>
    /// splits it before this is reached.
    /// </remarks>
    public ValueTask<string> TranscribeAsync(
        ReadOnlyMemory<float> samples,
        IReadOnlyList<string> biasPhrases,
        CancellationToken cancellationToken)
    {
        if (_recognizer is null || samples.Length == 0) return ValueTask.FromResult(string.Empty);

        cancellationToken.ThrowIfCancellationRequested();

        // The worker already owns an exact-sized array. Sherpa accepts the whole array,
        // so only sliced or non-array memory needs another copy.
        var waveform = MemoryMarshal.TryGetArray(samples, out var segment) && segment.Offset == 0
            && segment.Array is { } array && segment.Count == array.Length ? array : samples.ToArray();
        return ValueTask.FromResult(_recognizer.Transcribe(waveform, _hotwords!.Format(biasPhrases)));
    }

    /// <inheritdoc />
    public ValueTask DisposeAsync()
    {
        _recognizer?.Dispose();
        _recognizer = null;
        _hotwords = null;
        return ValueTask.CompletedTask;
    }
}
