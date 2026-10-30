using System.Text.Json.Serialization;

namespace Freehand.Cleanup;

internal sealed record ChatMessage([property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content")] string Content);
internal sealed record ChatTemplateOptions([property: JsonPropertyName("enable_thinking")] bool EnableThinking = false);
internal sealed record ChatRequest(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("messages")] ChatMessage[] Messages,
    [property: JsonPropertyName("max_tokens")] int MaxTokens,
    [property: JsonPropertyName("chat_template_kwargs")] ChatTemplateOptions ChatTemplateKwargs)
{
    [JsonPropertyName("stream")] public bool Stream { get; init; }
    [JsonPropertyName("temperature")] public int Temperature { get; init; }
    [JsonPropertyName("seed")] public int Seed { get; init; }
    [JsonPropertyName("cache_prompt")] public bool CachePrompt { get; init; }
}
internal sealed record CompletionRequest([property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("n_predict")] int MaxTokens)
{
    [JsonPropertyName("stream")] public bool Stream { get; init; }
    [JsonPropertyName("temperature")] public int Temperature { get; init; }
    [JsonPropertyName("seed")] public int Seed { get; init; }
    [JsonPropertyName("cache_prompt")] public bool CachePrompt { get; init; }
    [JsonPropertyName("stop")] public string[] Stop { get; } = ["<|im_end|>", "<|im_start|>"];
}
internal sealed record TokenizeRequest([property: JsonPropertyName("content")] string Content)
{
    [JsonPropertyName("add_special")] public bool AddSpecial { get; init; } = true;
    [JsonPropertyName("parse_special")] public bool ParseSpecial { get; init; } = true;
}

[JsonSerializable(typeof(ChatRequest))]
[JsonSerializable(typeof(CompletionRequest))]
[JsonSerializable(typeof(TokenizeRequest))]
internal sealed partial class CleanupJsonContext : JsonSerializerContext;
