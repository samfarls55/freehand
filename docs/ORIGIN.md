# Source record

Freehand derives from the Windows implementation in [Pat Simmons's Murmur repository](https://github.com/per-simmons/murmur-youtube). The migration began from `main` at commit `b3b45abbf2121980fffa6e468f7f8d62856cdd73`, with existing local modifications retained.

On October 8, 2026, the Windows solution, source, and tests moved into a standalone project. All 50 moved files were checked against their original SHA-256 hashes before adapting the layout. The shared dictionary vectors were copied so the original checkout retained its behavior contract. Build paths and test references were adjusted for the new project root.

Seven files already had local modifications. Their versions were preserved at migration:

- `src/Murmur.App/Murmur.App.csproj`
- `src/Murmur.App/Program.cs`
- `src/Murmur.App/SelfTest.cs`
- `src/Murmur.App/Views/TranscriptionsView.cs`
- `src/Murmur.Core/DictationEngine.cs`
- `src/Murmur.Testing/Fakes.cs`
- `tests/Murmur.App.Tests/UiTests.cs`

Subsequent Windows work added the owned speech worker, idle unloading, retained-audio retry, focus-aware text delivery, per-user installer, bundled model verification, and lifecycle tests.

On October 9, 2026, the project was renamed Freehand. The solution, projects, namespaces, application, and installer now use Freehand. User data lives under `%LOCALAPPDATA%\Freehand`, and the default installation lives under `%LOCALAPPDATA%\Programs\Freehand`.

The public Freehand repository starts with one initial commit containing the prepared codebase. Earlier development history, migration hashes, and local verification records are retained privately outside the published history. The original copyright attribution remains in the build metadata.

## License status

The upstream repository had no license file when Freehand was prepared for publication. No new application license has been added. This public source record preserves attribution without claiming a general right to reuse or redistribute the application code. The bundled model and third-party dependencies retain their separate licenses and notices.
