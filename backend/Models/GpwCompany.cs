namespace StockPilot.Api.Models;

/// <summary>
/// A company listed on the Warsaw Stock Exchange (GPW), as identified on stooq.pl.
/// </summary>
public sealed record GpwCompany
{
    /// <summary>
    /// Stooq ticker symbol (always lower-case, the form used in stooq.pl URLs),
    /// e.g. <c>"kgh"</c> for KGHM.
    /// </summary>
    public required string Ticker { get; init; }

    /// <summary>Full company name, e.g. <c>"KGHM Polska Miedź"</c>.</summary>
    public required string Name { get; init; }

    /// <summary>Optional GPW sector / industry classification.</summary>
    public string? Sector { get; init; }
}
