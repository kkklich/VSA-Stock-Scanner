using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Caching.Memory;
using StockPilot.Api.Models;
using StockPilot.Api.Services;

namespace StockPilot.Api.Controllers;

/// <summary>
/// Market-data endpoints backed by stooq.pl: the tracked GPW company list and
/// per-ticker end-of-day price history.
/// </summary>
[ApiController]
[Route("api/stocks")]
[Produces("application/json")]
public sealed class StocksController : ControllerBase
{
    private static readonly TimeSpan HistoryCacheDuration = TimeSpan.FromHours(6);

    private readonly IGpwCompanyService _companies;
    private readonly IStooqClient _stooq;
    private readonly IMemoryCache _cache;
    private readonly ILogger<StocksController> _logger;

    public StocksController(
        IGpwCompanyService companies,
        IStooqClient stooq,
        IMemoryCache cache,
        ILogger<StocksController> logger)
    {
        _companies = companies;
        _stooq = stooq;
        _cache = cache;
        _logger = logger;
    }

    /// <summary>Returns the list of GPW companies the scanner tracks.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(IReadOnlyList<GpwCompany>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<GpwCompany>>> GetCompanies(CancellationToken cancellationToken)
    {
        var companies = await _companies.GetCompaniesAsync(cancellationToken);
        return Ok(companies);
    }

    /// <summary>
    /// Returns a ticker's end-of-day OHLCV history from stooq.pl.
    /// </summary>
    /// <param name="ticker">Stooq ticker, e.g. <c>kgh</c>.</param>
    /// <param name="from">Optional inclusive start date (defaults to all available history).</param>
    /// <param name="to">Optional inclusive end date.</param>
    [HttpGet("{ticker}/history")]
    [ProducesResponseType(typeof(StockHistoryResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<StockHistoryResponse>> GetHistory(
        string ticker,
        [FromQuery] DateOnly? from,
        [FromQuery] DateOnly? to,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ticker))
        {
            return BadRequest("A ticker is required.");
        }

        if (from is { } f && to is { } t && f > t)
        {
            return BadRequest("'from' must not be later than 'to'.");
        }

        var normalizedTicker = ticker.Trim().ToLowerInvariant();
        var cacheKey = $"history:{normalizedTicker}:{from}:{to}";

        if (_cache.TryGetValue(cacheKey, out StockHistoryResponse? cached) && cached is not null)
        {
            return Ok(cached);
        }

        try
        {
            var company = await _companies.FindAsync(normalizedTicker, cancellationToken);
            var quotes = await _stooq.GetDailyHistoryAsync(normalizedTicker, from, to, cancellationToken);

            var response = new StockHistoryResponse
            {
                Ticker = normalizedTicker.ToUpperInvariant(),
                Name = company?.Name,
                Quotes = quotes,
            };

            _cache.Set(cacheKey, response, HistoryCacheDuration);
            return Ok(response);
        }
        catch (StooqAccessException ex)
        {
            _logger.LogWarning(ex, "stooq.pl access failed for ticker {Ticker}.", normalizedTicker);
            return Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status502BadGateway,
                title: "Upstream data provider (stooq.pl) unavailable");
        }
    }
}
