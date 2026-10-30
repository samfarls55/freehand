using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class ModelResolverTests
{
    [Fact]
    public void The_bundled_model_contract_uses_the_small_transducer()
    {
        ModelResolver.FeatureDimension.ShouldBe(80);
        ModelResolver.PreferredMaxSegmentSeconds.ShouldBe(15);
        ModelResolver.DirectoryName.ShouldBe("parakeet-110m");
        ModelResolver.Version.ShouldStartWith("parakeet-tdt-110m-int8/");
        using var models = new ModelResolver();
        models.BundledDirectory.ShouldEndWith(Path.Combine("models", "parakeet-110m"));
        ParakeetTranscriber.DefaultSearchPaths().ShouldAllBe(path => path.EndsWith("parakeet-110m", StringComparison.Ordinal));
    }
    [Fact]
    public async Task Missing_model_is_an_actionable_result_instead_of_an_exception()
    {
        using var models = new ModelResolver(baseDirectory: Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N")));
        (await models.VerifyAsync(CancellationToken.None)).ShouldBeFalse();
        models.IsVerified.ShouldBeFalse();
        (models.Error ?? "").ShouldContain("repair");
    }

    [Fact]
    public async Task Invalid_custom_path_can_return_to_the_bundled_selection()
    {
        using var models = new ModelResolver(customPath: "bad\0path");
        (await models.VerifyAsync(CancellationToken.None)).ShouldBeFalse();
        models.Select(null);
        models.ResolvedDirectory.ShouldBe(models.BundledDirectory);
    }
}
