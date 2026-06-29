namespace StockPilot.Api.Services;

/// <summary>
/// Thrown when stooq.pl refuses to serve data — for example an unsolved anti-bot
/// challenge, an access denial ("Odmowa dostępu"), an exceeded daily download
/// limit, or an otherwise unrecognized (non-CSV) response.
/// </summary>
public sealed class StooqAccessException : Exception
{
    public StooqAccessException(string message) : base(message)
    {
    }

    public StooqAccessException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
