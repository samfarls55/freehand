namespace Freehand.Core;

/// <summary>Preserved user data, with an isolated profile override for release verification.</summary>
public static class AppDataPaths
{
    /// <summary>Normal installations keep data in LocalAppData/Freehand.</summary>
    public static string DirectoryPath => Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY") is { Length: > 0 } path
        ? Path.GetFullPath(path)
        : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand");
}
