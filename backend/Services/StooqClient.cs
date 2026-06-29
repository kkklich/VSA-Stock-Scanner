using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using StockPilot.Api.Models;

namespace StockPilot.Api.Services;

/// <summary>
/// Typed <see cref="HttpClient"/> client for stooq.pl.
/// </summary>
/// <remarks>
/// stooq.pl guards its CSV endpoints with a hashcash-style proof-of-work challenge:
/// the page ships a constant <c>c</c> and a difficulty <c>d</c>, and the browser must
/// find an integer <c>n</c> such that the hex of <c>SHA-256(c + n)</c> starts with
/// <c>d</c> leading zeros, then POST <c>c</c> and <c>n</c> to <c>/__verify</c> to obtain
/// an auth cookie. This client solves that challenge automatically and retries the
/// original request. The shared <see cref="System.Net.CookieContainer"/> (configured in
/// <c>Program.cs</c>) keeps the auth cookie across calls.
/// </remarks>
public sealed partial class StooqClient : IStooqClient
{
    /// <summary>Safety cap on proof-of-work iterations (difficulty 4 averages ~65k).</summary>
    private const long MaxProofOfWorkIterations = 100_000_000;

    private static readonly string[] DenialMarkers =
    [
        "Odmowa dostępu",                   // access denied
        "Przekroczony",                     // limit exceeded
        "Exceeded the daily hits limit",
        "Brak danych",                      // no data
        "Wybrana lokalizacja nie istnieje", // location does not exist
        "requires JavaScript",
    ];

    private readonly HttpClient _http;
    private readonly ILogger<StooqClient> _logger;

    public StooqClient(HttpClient http, ILogger<StooqClient> logger)
    {
        _http = http;
        _logger = logger;
    }

    public async Task<IReadOnlyList<StooqDailyQuote>> GetDailyHistoryAsync(
        string ticker,
        DateOnly? from = null,
        DateOnly? to = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(ticker))
        {
            throw new ArgumentException("Ticker must be provided.", nameof(ticker));
        }

        var url = BuildDailyUrl(ticker.Trim().ToLowerInvariant(), from, to);
        var csv = await GetWithChallengeAsync(url, cancellationToken);
        return ParseDailyCsv(csv, ticker);
    }

    private static string BuildDailyUrl(string ticker, DateOnly? from, DateOnly? to)
    {
        // https://stooq.pl/q/d/l/?s=kgh&i=d[&d1=YYYYMMDD&d2=YYYYMMDD]
        var url = new StringBuilder("https://stooq.pl/q/d/l/?s=")
            .Append(Uri.EscapeDataString(ticker))
            .Append("&i=d");

        if (from is { } f)
        {
            url.Append("&d1=").Append(f.ToString("yyyyMMdd", CultureInfo.InvariantCulture));
        }

        if (to is { } t)
        {
            url.Append("&d2=").Append(t.ToString("yyyyMMdd", CultureInfo.InvariantCulture));
        }

        return url.ToString();
    }

    /// <summary>
    /// Performs a GET, transparently solving and clearing the anti-bot challenge if it
    /// appears, then returns the (CSV) response body.
    /// </summary>
    private async Task<string> GetWithChallengeAsync(string url, CancellationToken cancellationToken)
    {
        var body = await _http.GetStringAsync(url, cancellationToken);

        var challenge = ChallengeRegex().Match(body);
        if (challenge.Success)
        {
            _logger.LogDebug("stooq.pl issued an anti-bot challenge; solving proof-of-work.");

            var c = challenge.Groups["c"].Value;
            var difficulty = int.Parse(challenge.Groups["d"].Value, CultureInfo.InvariantCulture);
            var n = SolveProofOfWork(c, difficulty, cancellationToken);

            var verifyUrl = new Uri(new Uri(url).GetLeftPart(UriPartial.Authority) + "/__verify");
            using var form = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["c"] = c,
                ["n"] = n.ToString(CultureInfo.InvariantCulture),
            });

            using var verifyResponse = await _http.PostAsync(verifyUrl, form, cancellationToken);
            verifyResponse.EnsureSuccessStatusCode();

            body = await _http.GetStringAsync(url, cancellationToken);
            if (ChallengeRegex().IsMatch(body))
            {
                throw new StooqAccessException("stooq.pl re-issued the anti-bot challenge after verification.");
            }
        }

        EnsureNotBlocked(body);
        return body;
    }

    /// <summary>
    /// Finds the smallest non-negative integer <c>n</c> such that the hex of
    /// <c>SHA-256(challenge + n)</c> begins with <paramref name="difficulty"/> zero nibbles.
    /// </summary>
    private static long SolveProofOfWork(string challenge, int difficulty, CancellationToken cancellationToken)
    {
        var challengeBytes = Encoding.UTF8.GetBytes(challenge);
        Span<byte> hash = stackalloc byte[SHA256.HashSizeInBytes];

        for (long n = 0; n < MaxProofOfWorkIterations; n++)
        {
            if ((n & 0xFFFF) == 0)
            {
                cancellationToken.ThrowIfCancellationRequested();
            }

            var suffix = n.ToString(CultureInfo.InvariantCulture);
            var input = new byte[challengeBytes.Length + suffix.Length];
            challengeBytes.CopyTo(input, 0);
            Encoding.ASCII.GetBytes(suffix, 0, suffix.Length, input, challengeBytes.Length);

            SHA256.HashData(input, hash);
            if (HasLeadingZeroNibbles(hash, difficulty))
            {
                return n;
            }
        }

        throw new StooqAccessException(
            $"Could not solve the stooq.pl proof-of-work within {MaxProofOfWorkIterations} attempts.");
    }

    private static bool HasLeadingZeroNibbles(ReadOnlySpan<byte> hash, int nibbles)
    {
        for (var i = 0; i < nibbles; i++)
        {
            var b = hash[i / 2];
            var nibble = (i % 2 == 0) ? (b >> 4) : (b & 0x0F);
            if (nibble != 0)
            {
                return false;
            }
        }

        return true;
    }

    private static void EnsureNotBlocked(string body)
    {
        foreach (var marker in DenialMarkers)
        {
            if (body.Contains(marker, StringComparison.OrdinalIgnoreCase))
            {
                var snippet = body.Trim();
                snippet = snippet[..Math.Min(160, snippet.Length)];
                throw new StooqAccessException($"stooq.pl denied the request: \"{snippet}\"");
            }
        }
    }

    private static IReadOnlyList<StooqDailyQuote> ParseDailyCsv(string csv, string ticker)
    {
        var quotes = new List<StooqDailyQuote>();
        using var reader = new StringReader(csv);

        // stooq returns "Date,Open,High,Low,Close,Volume" (or the Polish equivalent) as the
        // first line. We parse positionally and skip any row whose first column is not a date.
        while (reader.ReadLine() is { } line)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var columns = line.Split(',');
            if (columns.Length < 6)
            {
                continue;
            }

            if (!DateOnly.TryParse(columns[0], CultureInfo.InvariantCulture, DateTimeStyles.None, out var date) ||
                !decimal.TryParse(columns[1], NumberStyles.Any, CultureInfo.InvariantCulture, out var open) ||
                !decimal.TryParse(columns[2], NumberStyles.Any, CultureInfo.InvariantCulture, out var high) ||
                !decimal.TryParse(columns[3], NumberStyles.Any, CultureInfo.InvariantCulture, out var low) ||
                !decimal.TryParse(columns[4], NumberStyles.Any, CultureInfo.InvariantCulture, out var close))
            {
                continue;
            }

            // Volume can be blank (e.g. for indices) — treat as zero.
            long.TryParse(columns[5], NumberStyles.Any, CultureInfo.InvariantCulture, out var volume);

            quotes.Add(new StooqDailyQuote
            {
                Date = date,
                Open = open,
                High = high,
                Low = low,
                Close = close,
                Volume = volume,
            });
        }

        if (quotes.Count == 0)
        {
            throw new StooqAccessException($"stooq.pl returned no parseable daily data for '{ticker}'.");
        }

        return quotes;
    }

    /// <summary>Matches the inline proof-of-work challenge, e.g. <c>c="AAA...",d=4</c>.</summary>
    [GeneratedRegex("""c="(?<c>[^"]+)",d=(?<d>\d+)""", RegexOptions.CultureInvariant)]
    private static partial Regex ChallengeRegex();
}
