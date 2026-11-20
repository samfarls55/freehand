using System.Text.Json.Serialization;

namespace Freehand.Cleanup;

internal sealed record TranscriptInput([property: JsonPropertyName("transcript")] string Transcript);
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
    [JsonPropertyName("temperature")] public double Temperature { get; init; }
    [JsonPropertyName("seed")] public int Seed { get; init; }
    [JsonPropertyName("cache_prompt")] public bool CachePrompt { get; init; }
}
internal sealed record CompletionRequest([property: JsonPropertyName("prompt")] int[] Prompt,
    [property: JsonPropertyName("n_predict")] int MaxTokens)
{
    [JsonPropertyName("stream")] public bool Stream { get; init; }
    [JsonPropertyName("temperature")] public double Temperature { get; init; }
    [JsonPropertyName("seed")] public int Seed { get; init; }
    [JsonPropertyName("cache_prompt")] public bool CachePrompt { get; init; }
    [JsonPropertyName("stop")] public string[] Stop { get; init; } = ["<|im_end|>", "<|im_start|>"];
    [JsonPropertyName("repeat_penalty")] public double RepeatPenalty { get; init; } = 1;
    [JsonPropertyName("add_special")] public bool AddSpecial { get; init; } = true;
    [JsonPropertyName("parse_special")] public bool ParseSpecial { get; init; } = true;
}
internal sealed record TokenizeRequest([property: JsonPropertyName("content")] string Content)
{
    [JsonPropertyName("add_special")] public bool AddSpecial { get; init; } = true;
    [JsonPropertyName("parse_special")] public bool ParseSpecial { get; init; } = true;
}

[JsonSerializable(typeof(ChatRequest))]
[JsonSerializable(typeof(CompletionRequest))]
[JsonSerializable(typeof(TokenizeRequest))]
[JsonSerializable(typeof(TranscriptInput))]
internal sealed partial class CleanupJsonContext : JsonSerializerContext;
