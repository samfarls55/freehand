using Freehand.Speech;
using Shouldly;
using Xunit;

namespace Freehand.CoreTests;

public sealed class ModelResolverTests
{
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
