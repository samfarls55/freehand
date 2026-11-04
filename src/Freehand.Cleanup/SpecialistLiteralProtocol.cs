namespace Freehand.Cleanup;

/// <summary>The explicitly selected specialist literal adapter; general-model contracts are unchanged.</summary>
public enum SpecialistLiteralProtocol
{
    /// <summary>Existing dictionary and paired double-quote masking.</summary>
    CompactV3,
    /// <summary>Strict balanced double- and single-quote masking with apostrophe boundaries.</summary>
    CompactV4,
}
