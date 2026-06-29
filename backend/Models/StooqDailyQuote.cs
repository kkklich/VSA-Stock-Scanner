namespace StockPilot.Api.Models;

/// <summary>
/// One end-of-day (EOD) OHLCV bar for a ticker, as returned by stooq.pl.
/// </summary>
public sealed record StooqDailyQuote
{
    /// <summary>Session date (the trading day this bar belongs to).</summary>
    public required DateOnly Date { get; init; }

    /// <summary>Opening price in PLN.</summary>
    public required decimal Open { get; init; }

    /// <summary>Highest price of the session in PLN.</summary>
    public required decimal High { get; init; }

    /// <summary>Lowest price of the session in PLN.</summary>
    public required decimal Low { get; init; }

    /// <summary>Closing price in PLN.</summary>
    public required decimal Close { get; init; }

    /// <summary>Number of shares traded during the session.</summary>
    public required long Volume { get; init; }
}
