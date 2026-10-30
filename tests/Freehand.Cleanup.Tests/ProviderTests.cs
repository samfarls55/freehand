using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Freehand.Abstractions;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class ProviderTests
{
    [Fact]
    public async Task Quill_uses_prescribed_raw_contract_and_private_owned_worker()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        await using var provider = fixture.Provider();
        (await provider.ProcessAsync("um send it Friday", CancellationToken.None)).ShouldBe("Send it Friday.");
        fixture.Transport.Paths.ShouldBe(["/health", "/tokenize", "/completion"]);
        fixture.Launcher.Start!.Arguments.ShouldNotContain("--jinja");
        fixture.Launcher.Start.Arguments.ShouldContain("--offline");
        fixture.Launcher.Start.Arguments.ShouldContain("--no-context-shift");
        fixture.Launcher.Start.Arguments.ShouldContain("--log-disable");
        fixture.Launcher.Start.EnvironmentVariables["LLAMA_API_KEY"].Length.ShouldBe(64);
        fixture.Transport.CompletionPrompt.ShouldBe("<|im_start|>system\nYou clean up dictated text.<|im_end|>\n"
            + "<|im_start|>user\num send it Friday<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n");
        fixture.Transport.AllAuthenticated.ShouldBeTrue();
        fixture.Transport.Temperature.ShouldBe(0);
        fixture.Transport.Stream.ShouldBeFalse();
    }

    [Theory]
    [InlineData(CleanupPromptStyle.Qwen35)]
    [InlineData(CleanupPromptStyle.Ministral3)]
    [InlineData(CleanupPromptStyle.Gemma4)]
    public async Task General_models_use_embedded_template_and_disable_thinking(CleanupPromptStyle style)
    {
        using var fixture = new Fixture(style);
        await using var provider = fixture.Provider();
        (await provider.ProcessAsync("um send it Friday", CancellationToken.None)).ShouldBe("Send it Friday.");
        fixture.Transport.Paths.ShouldBe(["/health", "/apply-template", "/tokenize", "/v1/chat/completions"]);
        fixture.Launcher.Start!.Arguments.ShouldContain("--jinja");
        fixture.Transport.EnableThinking.ShouldBeFalse();
        fixture.Transport.SystemPrompt!.ShouldContain("Preserve the speaker's meaning");
        fixture.Transport.SystemPrompt!.ShouldContain("[[FREEHAND_LITERAL_");
        fixture.Transport.Transcript.ShouldBe("um send it Friday");
    }

    [Theory]
    [InlineData("{\"content\":\"partial\",\"stop_type\":\"limit\",\"truncated\":false}")]
    [InlineData("{\"content\":\"partial\",\"stop_type\":\"eos\",\"truncated\":true}")]
    [InlineData("{\"content\":\"<think>private text</think>answer\",\"stop_type\":\"eos\"}")]
    [InlineData("{\"content\":\"\",\"stop_type\":\"eos\"}")]
    [InlineData("{\"content\":\"partial\"}")]
    public async Task Native_incomplete_or_control_output_is_rejected_and_worker_stopped(string response)
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.NativeResponse = response;
        await using var provider = fixture.Provider();
        await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        fixture.Launcher.Workers.Single().Terminated.ShouldBeTrue();
    }

    [Theory]
    [InlineData("length", null)]
    [InlineData("tool_calls", null)]
    [InlineData("stop", "reasoning text")]
    public async Task Chat_must_finish_normally_without_reasoning(string finishReason, string? reasoning)
    {
        using var fixture = new Fixture(CleanupPromptStyle.Qwen35);
        fixture.Transport.FinishReason = finishReason;
        fixture.Transport.Reasoning = reasoning;
        await using var provider = fixture.Provider();
        await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        fixture.Launcher.Workers.Single().Terminated.ShouldBeTrue();
    }

    [Fact]
    public async Task Input_budget_rejects_before_generation_without_truncating()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.TokenCount = 255;
        await using var provider = fixture.Provider(fixture.Options with { ContextSize = 256, MaxOutputTokens = 32 });
        await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("complete original", CancellationToken.None));
        fixture.Transport.Paths.ShouldNotContain("/completion");
        fixture.Launcher.Workers.Single().Terminated.ShouldBeTrue();
    }

    [Fact]
    public async Task Missing_or_hash_mismatched_artifacts_never_start_worker()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        await using var provider = fixture.Provider(fixture.Options with { ModelSha256 = new string('0', 64) });
        await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        fixture.Launcher.Workers.ShouldBeEmpty();
    }

    [Fact]
    public async Task Worker_restart_reverifies_changed_model_artifact()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        await using var provider = fixture.Provider();
        await provider.ProcessAsync("first request", CancellationToken.None);
        fixture.Launcher.Workers[0].Terminate();
        await File.WriteAllTextAsync(fixture.Options.ModelPath, "a different model");
        await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("second request", CancellationToken.None));
        fixture.Launcher.Workers.Count.ShouldBe(1);
    }

    [Fact]
    public async Task Bundle_dependency_hash_mismatch_prevents_runtime_launch()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        var directory = Path.GetDirectoryName(fixture.Options.RuntimePath)!;
        var dependency = Path.Combine(directory, "llama.dll");
        await File.WriteAllTextAsync(dependency, "measured dependency");
        var hash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(dependency)));
        var options = fixture.Options with
        {
            BundleDirectory = directory,
            Artifacts =
            [
                new CleanupArtifactHash(fixture.Options.RuntimePath, fixture.Options.RuntimeSha256),
                new CleanupArtifactHash(fixture.Options.ModelPath, fixture.Options.ModelSha256),
                new CleanupArtifactHash(dependency, hash, new FileInfo(dependency).Length),
            ],
        };
        await File.WriteAllTextAsync(dependency, "modified dependency");
        await using var provider = fixture.Provider(options);
        var error = await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        error.Message.ShouldContain("manifest hash");
        fixture.Launcher.Workers.ShouldBeEmpty();
    }

    [Fact]
    public async Task Bundle_size_metadata_is_verified_before_runtime_launch()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        var options = fixture.Options with
        {
            BundleDirectory = Path.GetDirectoryName(fixture.Options.RuntimePath),
            Artifacts =
            [
                new CleanupArtifactHash(fixture.Options.RuntimePath, fixture.Options.RuntimeSha256, 999),
                new CleanupArtifactHash(fixture.Options.ModelPath, fixture.Options.ModelSha256),
            ],
        };
        await using var provider = fixture.Provider(options);
        var error = await Should.ThrowAsync<InvalidDataException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        error.Message.ShouldContain("manifest size");
        fixture.Launcher.Workers.ShouldBeEmpty();
    }

    [Fact]
    public async Task Cancelled_request_stops_generation_and_fresh_request_gets_new_worker_and_secret()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.BlockGeneration = true;
        await using var provider = fixture.Provider();
        using var cancellation = new CancellationTokenSource();
        var processing = provider.ProcessAsync("first request", cancellation.Token).AsTask();
        await fixture.Transport.GenerationStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var secret = fixture.Launcher.Start!.EnvironmentVariables["LLAMA_API_KEY"];
        await cancellation.CancelAsync();
        await Should.ThrowAsync<OperationCanceledException>(async () => await processing);
        fixture.Launcher.Workers[0].Terminated.ShouldBeTrue();
        fixture.Transport.BlockGeneration = false;
        (await provider.ProcessAsync("second request", CancellationToken.None)).ShouldBe("Send it Friday.");
        fixture.Launcher.Workers.Count.ShouldBe(2);
        fixture.Launcher.Start!.EnvironmentVariables["LLAMA_API_KEY"].ShouldNotBe(secret);
    }

    [Fact]
    public async Task Idle_unload_releases_worker_and_reloads_on_next_request()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        await using var provider = fixture.Provider(fixture.Options with { IdleTimeout = TimeSpan.FromMilliseconds(20) });
        await provider.ProcessAsync("first request", CancellationToken.None);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!fixture.Launcher.Workers[0].Disposed) await Task.Delay(10, deadline.Token);
        await provider.ProcessAsync("second request", CancellationToken.None);
        fixture.Launcher.Workers.Count.ShouldBe(2);
    }

    [Fact]
    public async Task Already_cancelled_request_does_not_disable_existing_idle_unload()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        await using var provider = fixture.Provider(fixture.Options with { IdleTimeout = TimeSpan.FromMilliseconds(20) });
        await provider.ProcessAsync("first request", CancellationToken.None);
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();
        await Should.ThrowAsync<OperationCanceledException>(async () => await provider.ProcessAsync("cancelled request", cancellation.Token));
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!fixture.Launcher.Workers[0].Disposed) await Task.Delay(10, deadline.Token);
    }

    [Fact]
    public async Task Disposal_cancels_active_inference_and_owns_worker_until_exit()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.BlockGeneration = true;
        var provider = fixture.Provider();
        var processing = provider.ProcessAsync("dictated text", CancellationToken.None).AsTask();
        await fixture.Transport.GenerationStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await provider.DisposeAsync();
        await Should.ThrowAsync<OperationCanceledException>(async () => await processing);
        fixture.Launcher.Workers.Single().Disposed.ShouldBeTrue();
        await Should.ThrowAsync<ObjectDisposedException>(async () => await provider.ProcessAsync("another request", CancellationToken.None));
    }

    [Fact]
    public async Task Readiness_failure_is_bounded_and_worker_is_terminated()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.Ready = false;
        await using var provider = fixture.Provider(fixture.Options with { StartupTimeout = TimeSpan.FromMilliseconds(50) });
        await Should.ThrowAsync<TimeoutException>(async () => await provider.ProcessAsync("dictated text", CancellationToken.None));
        fixture.Launcher.Workers.Single().Terminated.ShouldBeTrue();
    }

    [Fact]
    public async Task Request_failure_never_exposes_response_or_transcript_in_exception()
    {
        using var fixture = new Fixture(CleanupPromptStyle.QuillChatMl);
        fixture.Transport.GenerationError = true;
        await using var provider = fixture.Provider();
        var error = await Should.ThrowAsync<HttpRequestException>(async () => await provider.ProcessAsync("private transcript sentinel", CancellationToken.None));
        error.ToString().ShouldNotContain("private transcript sentinel");
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-" + Guid.NewGuid().ToString("N"));
        private readonly HttpClient _http;
        public FakeLauncher Launcher { get; } = new();
        public FakeTransport Transport { get; }
        public LlamaCleanupOptions Options { get; }
        public Fixture(CleanupPromptStyle style)
        {
            Directory.CreateDirectory(_directory);
            var runtime = Path.Combine(_directory, "llama-server.exe");
            var model = Path.Combine(_directory, "model.gguf");
            File.WriteAllText(runtime, "test runtime");
            File.WriteAllText(model, "test model");
            Options = new LlamaCleanupOptions
            {
                RuntimePath = runtime, ModelPath = model, ModelId = "test-cleanup-model", PromptStyle = style,
                RuntimeSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(runtime))),
                ModelSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(model))),
            };
            Transport = new FakeTransport(Launcher);
            _http = new HttpClient(Transport);
        }
        public LlamaTranscriptPostProcessor Provider(LlamaCleanupOptions? options = null) => new(options ?? Options, Launcher, _http);
        public void Dispose() { _http.Dispose(); Directory.Delete(_directory, true); }
    }

    private sealed class FakeLauncher : ICleanupWorkerLauncher
    {
        public CleanupWorkerStartInfo? Start { get; private set; }
        public List<FakeWorker> Workers { get; } = [];
        public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo)
        {
            Start = startInfo;
            var worker = new FakeWorker();
            Workers.Add(worker);
            return worker;
        }
    }

    private sealed class FakeWorker : IWorkerProcess
    {
        public int Id => 1;
        public bool HasExited => Terminated;
        public bool Terminated { get; private set; }
        public bool Disposed { get; private set; }
        public Task WaitForExitAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public void Terminate() => Terminated = true;
        public ValueTask DisposeAsync() { Terminated = true; Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class FakeTransport(FakeLauncher launcher) : HttpMessageHandler
    {
        public List<string> Paths { get; } = [];
        public string? CompletionPrompt { get; private set; }
        public string? SystemPrompt { get; private set; }
        public string? Transcript { get; private set; }
        public bool EnableThinking { get; private set; }
        public int Temperature { get; private set; }
        public bool Stream { get; private set; }
        public int TokenCount { get; set; } = 10;
        public string NativeResponse { get; set; } = "{\"content\":\"Send it Friday.\",\"stop_type\":\"eos\",\"truncated\":false}";
        public string FinishReason { get; set; } = "stop";
        public string? Reasoning { get; set; }
        public bool BlockGeneration { get; set; }
        public bool GenerationError { get; set; }
        public bool Ready { get; set; } = true;
        public bool AllAuthenticated { get; private set; } = true;
        public TaskCompletionSource GenerationStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            request.RequestUri!.Host.ShouldBe("127.0.0.1");
            var path = request.RequestUri.AbsolutePath;
            Paths.Add(path);
            AllAuthenticated &= request.Headers.Authorization?.Scheme == "Bearer"
                && request.Headers.Authorization.Parameter == launcher.Start!.EnvironmentVariables["LLAMA_API_KEY"];
            if (path == "/health") return new HttpResponseMessage(Ready ? HttpStatusCode.OK : HttpStatusCode.ServiceUnavailable);
            using var input = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
            if (path == "/tokenize") return Json("{\"tokens\":[" + string.Join(',', Enumerable.Repeat("1", TokenCount)) + "]}");
            if (path == "/apply-template") return Json("{\"prompt\":\"embedded model chat template\"}");
            GenerationStarted.TrySetResult();
            if (BlockGeneration) await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            if (GenerationError) return new HttpResponseMessage(HttpStatusCode.InternalServerError) { Content = new StringContent("private transcript sentinel") };
            Temperature = input.RootElement.GetProperty("temperature").GetInt32();
            Stream = input.RootElement.GetProperty("stream").GetBoolean();
            if (path == "/completion")
            {
                CompletionPrompt = input.RootElement.GetProperty("prompt").GetString();
                return Json(NativeResponse);
            }
            if (path == "/v1/chat/completions")
            {
                EnableThinking = input.RootElement.GetProperty("chat_template_kwargs").GetProperty("enable_thinking").GetBoolean();
                SystemPrompt = input.RootElement.GetProperty("messages")[0].GetProperty("content").GetString();
                Transcript = input.RootElement.GetProperty("messages")[1].GetProperty("content").GetString();
                return Json("{\"choices\":[{\"finish_reason\":" + JsonSerializer.Serialize(FinishReason)
                    + ",\"message\":{\"content\":\"Send it Friday.\",\"reasoning_content\":" + JsonSerializer.Serialize(Reasoning) + "}}]}");
            }
            throw new InvalidOperationException("Unexpected endpoint.");
        }
        private static HttpResponseMessage Json(string json) => new(HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
    }
}
