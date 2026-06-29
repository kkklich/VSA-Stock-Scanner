using StockPilot.Api.Models;

namespace StockPilot.Api.Services;

/// <summary>
/// Client for fetching market data from stooq.pl. Implementations transparently
/// handle stooq's anti-bot proof-of-work challenge.
/// </summary>
public interface IStooqClient
{
    /// <summary>
    /// Downloads end-of-day OHLCV history for a ticker, oldest bar first.
    /// </summary>
    /// <param name="ticker">Stooq ticker, e.g. <c>"kgh"</c>.</param>
    /// <param name="from">Optional inclusive start date.</param>
    /// <param name="to">Optional inclusive end date.</param>
    /// <exception cref="StooqAccessException">stooq.pl refused or returned no usable data.</exception>
    Task<IReadOnlyList<StooqDailyQuote>> GetDailyHistoryAsync(
        string ticker,
        DateOnly? from = null,
        DateOnly? to = null,
        CancellationToken cancellationToken = default);
}
