namespace StockPilot.Api.Models;

/// <summary>
/// Response payload for <c>GET /api/stocks/{ticker}/history</c>: a ticker's
/// end-of-day price history pulled from stooq.pl.
/// </summary>
public sealed record StockHistoryResponse
{
    /// <summary>Ticker the history belongs to (upper-case for display).</summary>
    public required string Ticker { get; init; }

    /// <summary>
    /// Company name, when the ticker is known in the GPW company list; otherwise <c>null</c>.
    /// </summary>
    public string? Name { get; init; }

    /// <summary>Chronological list of EOD OHLCV bars (oldest first).</summary>
    public required IReadOnlyList<StooqDailyQuote> Quotes { get; init; }
}
