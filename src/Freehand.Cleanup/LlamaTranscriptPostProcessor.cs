using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text.Json;
using Freehand.Abstractions;

namespace Freehand.Cleanup;

/// <summary>Runs one pinned local text model behind an authenticated loopback llama-server.</summary>
/// <remarks>Only complete responses are returned. The caller owns transcript fallback and delivery.</remarks>
public sealed class LlamaTranscriptPostProcessor : ITranscriptPostProcessor
{
    private const int MaximumResponseBytes = 2 * 1024 * 1024;
    private readonly LlamaCleanupOptions _options;
    private readonly ICleanupWorkerLauncher _launcher;
    private readonly HttpClient _http;
    private readonly bool _ownsHttp;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly CancellationTokenSource _lifetime = new();
    private readonly object _idleSync = new();
    private CancellationTokenSource? _idleCancellation;
    private Task _idleTask = Task.CompletedTask;
    private IWorkerProcess? _process;
    private Uri? _endpoint;
    private string? _apiKey;
    private int _disposed;

    /// <summary>Creates a lazy local processor; artifact hashing and loading happen on first use.</summary>
    /// <param name="options">Explicit pinned local artifacts and inference settings.</param>
    /// <param name="launcher">Platform-owned process and process-tree lifetime implementation.</param>
    /// <param name="httpClient">Optional caller-owned transport for testing; production uses a proxy-free, redirect-free local transport.</param>
    public LlamaTranscriptPostProcessor(LlamaCleanupOptions options, ICleanupWorkerLauncher launcher, HttpClient? httpClient = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(launcher);
        options.Validate();
        _options = options with { Artifacts = options.Artifacts.ToArray() };
        _launcher = launcher;
        _ownsHttp = httpClient is null;
        _http = httpClient ?? new HttpClient(new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false })
            { Timeout = Timeout.InfiniteTimeSpan };
    }

    /// <inheritdoc />
    public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(text);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _lifetime.Token);
        await _gate.WaitAsync(linked.Token).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
            CancelIdle();
            await EnsureWorkerAsync(linked.Token).ConfigureAwait(false);
            string output;
            if (_options.PromptStyle == CleanupPromptStyle.QuillChatMl)
            {
                if (text.Contains("<|im_start|>", StringComparison.Ordinal) || text.Contains("<|im_end|>", StringComparison.Ordinal))
                    throw new InvalidDataException("The transcript contains unsupported model control tokens.");
                var prompt = "<|im_start|>system\nYou clean up dictated text.<|im_end|>\n"
                    + "<|im_start|>user\n" + text + "<|im_end|>\n"
                    + "<|im_start|>assistant\n<think>\n\n</think>\n\n";
                await CheckBudgetAsync(prompt, linked.Token).ConfigureAwait(false);
                using var response = await PostAsync("completion", new CompletionRequest(prompt, _options.MaxOutputTokens),
                    CleanupJsonContext.Default.CompletionRequest, linked.Token).ConfigureAwait(false);
                output = CompleteNative(response.RootElement);
            }
            else
            {
                var request = new ChatRequest(_options.ModelId,
                    [new ChatMessage("system", CleanupPrompt.Text), new ChatMessage("user", text)],
                    _options.MaxOutputTokens, new ChatTemplateOptions());
                using var template = await PostAsync("apply-template", request, CleanupJsonContext.Default.ChatRequest, linked.Token).ConfigureAwait(false);
                if (!template.RootElement.TryGetProperty("prompt", out var formatted) || formatted.ValueKind != JsonValueKind.String)
                    throw new InvalidDataException("The cleanup runtime did not supply the model's chat template.");
                await CheckBudgetAsync(formatted.GetString()!, linked.Token).ConfigureAwait(false);
                using var response = await PostAsync("v1/chat/completions", request, CleanupJsonContext.Default.ChatRequest, linked.Token).ConfigureAwait(false);
                output = CompleteChat(response.RootElement);
            }
            if (string.IsNullOrWhiteSpace(output) || ContainsControlOutput(output))
                throw new InvalidDataException("Cleanup returned empty text or model control output.");
            return output;
        }
        catch
        {
            await StopWorkerAsync().ConfigureAwait(false);
            throw;
        }
        finally
        {
            ScheduleIdle();
            _gate.Release();
        }
    }

    private async Task EnsureWorkerAsync(CancellationToken token)
    {
        if (_process is { HasExited: false }) return;
        await StopWorkerAsync().ConfigureAwait(false);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(_options.StartupTimeout);
        try
        {
            if (_options.Artifacts.Count == 0)
            {
                await VerifyArtifactAsync(_options.RuntimePath, _options.RuntimeSha256, "runtime", null, deadline.Token).ConfigureAwait(false);
                await VerifyArtifactAsync(_options.ModelPath, _options.ModelSha256, "model", null, deadline.Token).ConfigureAwait(false);
            }
            else
            {
                foreach (var artifact in _options.Artifacts)
                    await VerifyArtifactAsync(artifact.Path, artifact.Sha256, "bundle artifact", artifact.Size, deadline.Token).ConfigureAwait(false);
            }
            var listener = new TcpListener(IPAddress.Loopback, 0);
            int port;
            try { listener.Start(); port = ((IPEndPoint)listener.LocalEndpoint).Port; }
            finally { listener.Stop(); }
            _endpoint = new Uri("http://127.0.0.1:" + port.ToString(CultureInfo.InvariantCulture) + "/", UriKind.Absolute);
            _apiKey = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
            var arguments = new List<string>
            {
                "--model", _options.ModelPath, "--alias", _options.ModelId,
                "--host", "127.0.0.1", "--port", port.ToString(CultureInfo.InvariantCulture),
                "--ctx-size", _options.ContextSize.ToString(CultureInfo.InvariantCulture),
                "--parallel", "1", "--threads", _options.Threads.ToString(CultureInfo.InvariantCulture),
                "--threads-batch", _options.Threads.ToString(CultureInfo.InvariantCulture),
                "--n-gpu-layers", _options.GpuLayers.ToString(CultureInfo.InvariantCulture),
                "--n-predict", _options.MaxOutputTokens.ToString(CultureInfo.InvariantCulture),
                "--fit", "off", "--no-context-shift", "--no-webui", "--no-slots", "--no-mmproj", "--offline", "--log-disable",
            };
            arguments.Add(_options.PromptStyle == CleanupPromptStyle.QuillChatMl ? "--no-jinja" : "--jinja");
            _process = _launcher.Launch(new CleanupWorkerStartInfo(_options.RuntimePath, arguments,
                new Dictionary<string, string>(StringComparer.Ordinal) { ["LLAMA_API_KEY"] = _apiKey }));
            while (true)
            {
                deadline.Token.ThrowIfCancellationRequested();
                if (_process.HasExited) throw new InvalidOperationException("The cleanup worker exited before its model was ready.");
                try
                {
                    using var request = Request(HttpMethod.Get, "health");
                    using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
                    if (response.IsSuccessStatusCode) return;
                    if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
                        throw new InvalidOperationException("Local cleanup worker authentication failed.");
                }
                catch (HttpRequestException) { /* The child may not have bound its socket yet. */ }
                await Task.Delay(TimeSpan.FromMilliseconds(100), deadline.Token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        {
            throw new TimeoutException("The cleanup model did not become ready within its startup deadline.");
        }
    }

    private static async Task VerifyArtifactAsync(string path, string expected, string label, long? size, CancellationToken token)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("The configured cleanup " + label + " is missing.", path);
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (size is not null && stream.Length != size) throw new InvalidDataException("The configured cleanup " + label + " does not match its manifest size.");
        var actual = Convert.ToHexString(await SHA256.HashDataAsync(stream, token).ConfigureAwait(false));
        if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The configured cleanup " + label + " does not match its manifest hash.");
    }

    private async Task CheckBudgetAsync(string prompt, CancellationToken token)
    {
        using var response = await PostAsync("tokenize", new TokenizeRequest(prompt), CleanupJsonContext.Default.TokenizeRequest, token).ConfigureAwait(false);
        if (!response.RootElement.TryGetProperty("tokens", out var tokens) || tokens.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("The cleanup runtime could not verify the input token budget.");
        if (tokens.GetArrayLength() > _options.ContextSize - _options.MaxOutputTokens)
            throw new InvalidDataException("The complete transcript and output do not fit the configured cleanup context.");
    }

    private HttpRequestMessage Request(HttpMethod method, string path)
    {
        if (_endpoint is null || _apiKey is null || _process is null || _process.HasExited)
            throw new InvalidOperationException("The cleanup worker is unavailable.");
        var request = new HttpRequestMessage(method, new Uri(_endpoint, path));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        return request;
    }

    private async Task<JsonDocument> PostAsync<T>(string path, T value, System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> type, CancellationToken token)
    {
        using var request = Request(HttpMethod.Post, path);
        request.Content = JsonContent.Create(value, type);
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode) throw new HttpRequestException("Local cleanup request failed.", null, response.StatusCode);
        if (response.Content.Headers.ContentLength > MaximumResponseBytes) throw new InvalidDataException("The cleanup response exceeds the allowed size.");
        await using var stream = await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);
        using var bytes = new MemoryStream();
        var buffer = new byte[8192];
        while (true)
        {
            var read = await stream.ReadAsync(buffer, token).ConfigureAwait(false);
            if (read == 0) break;
            if (bytes.Length + read > MaximumResponseBytes) throw new InvalidDataException("The cleanup response exceeds the allowed size.");
            bytes.Write(buffer, 0, read);
        }
        try { return JsonDocument.Parse(bytes.GetBuffer().AsMemory(0, checked((int)bytes.Length)), new JsonDocumentOptions { MaxDepth = 32 }); }
        catch (JsonException) { throw new InvalidDataException("The cleanup runtime returned malformed JSON."); }
    }

    private static string CompleteNative(JsonElement root)
    {
        var stopped = root.TryGetProperty("stop_type", out var kind)
            ? kind.ValueKind == JsonValueKind.String && kind.GetString() is "eos" or "word"
            : Flag(root, "stopped_eos") || Flag(root, "stopped_word");
        if (!stopped || Flag(root, "truncated") || Flag(root, "stopped_limit"))
            throw new InvalidDataException("Cleanup did not produce a complete response.");
        if (!root.TryGetProperty("content", out var content) || content.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("Cleanup did not return text.");
        return content.GetString()!;
    }

    private static string CompleteChat(JsonElement root)
    {
        if (Flag(root, "truncated") || !root.TryGetProperty("choices", out var choices)
            || choices.ValueKind != JsonValueKind.Array || choices.GetArrayLength() != 1)
            throw new InvalidDataException("Cleanup did not produce one complete response.");
        var choice = choices[0];
        if (!choice.TryGetProperty("finish_reason", out var finish) || finish.GetString() != "stop"
            || !choice.TryGetProperty("message", out var message)
            || !message.TryGetProperty("content", out var content) || content.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("Cleanup did not produce a complete text response.");
        if (message.TryGetProperty("reasoning_content", out var reasoning)
            && reasoning.ValueKind != JsonValueKind.Null && (reasoning.ValueKind != JsonValueKind.String || !string.IsNullOrWhiteSpace(reasoning.GetString())))
            throw new InvalidDataException("Cleanup returned unexpected reasoning output.");
        return content.GetString()!;
    }

    private static bool Flag(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;
    private static bool ContainsControlOutput(string value) => value.Contains("<think>", StringComparison.OrdinalIgnoreCase)
        || value.Contains("</think>", StringComparison.OrdinalIgnoreCase)
        || value.Contains("<|im_start|>", StringComparison.Ordinal) || value.Contains("<|im_end|>", StringComparison.Ordinal)
        || value.Contains("<|channel>", StringComparison.Ordinal) || value.Contains("<start_of_turn>", StringComparison.Ordinal);

    private void CancelIdle()
    {
        lock (_idleSync)
        {
            _idleCancellation?.Cancel();
            _idleCancellation?.Dispose();
            _idleCancellation = null;
        }
    }

    private void ScheduleIdle()
    {
        lock (_idleSync)
        {
            if (Volatile.Read(ref _disposed) != 0 || _process is null) return;
            _idleCancellation?.Cancel();
            _idleCancellation?.Dispose();
            _idleCancellation = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            _idleTask = UnloadWhenIdleAsync(_idleCancellation.Token);
        }
    }

    private async Task UnloadWhenIdleAsync(CancellationToken token)
    {
        try
        {
            await Task.Delay(_options.IdleTimeout, token).ConfigureAwait(false);
            await _gate.WaitAsync(token).ConfigureAwait(false);
            try { token.ThrowIfCancellationRequested(); await StopWorkerAsync().ConfigureAwait(false); }
            finally { _gate.Release(); }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
    }

    private async Task StopWorkerAsync()
    {
        var process = _process;
        _process = null;
        _endpoint = null;
        _apiKey = null;
        if (process is null) return;
        try { if (!process.HasExited) process.Terminate(); }
        finally { await process.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); }
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        await _lifetime.CancelAsync().ConfigureAwait(false);
        CancelIdle();
        try
        {
            await _gate.WaitAsync().ConfigureAwait(false);
            try { await StopWorkerAsync().ConfigureAwait(false); }
            finally { _gate.Release(); }
            await _idleTask.ConfigureAwait(false);
        }
        finally
        {
            if (_ownsHttp) _http.Dispose();
            _lifetime.Dispose();
            _gate.Dispose();
        }
    }
}
