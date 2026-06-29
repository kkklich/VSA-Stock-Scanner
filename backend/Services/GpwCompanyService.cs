using System.Text.Json;
using StockPilot.Api.Models;

namespace StockPilot.Api.Services;

/// <summary>
/// Loads the tracked GPW company list from <c>Data/gpw-companies.json</c> once and
/// caches it for the lifetime of the application.
/// </summary>
/// <remarks>
/// stooq.pl does not expose a reliable, free "all GPW companies" endpoint, so the
/// canonical list is maintained as a seed JSON file. The daily ingestion workflow
/// (see <c>agent/DOCUMENTATION.md</c> §11) can later replace or extend this source.
/// </remarks>
public sealed class GpwCompanyService : IGpwCompanyService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly string _filePath;
    private readonly ILogger<GpwCompanyService> _logger;
    private readonly SemaphoreSlim _gate = new(1, 1);

    private IReadOnlyList<GpwCompany>? _companies;

    public GpwCompanyService(ILogger<GpwCompanyService> logger)
    {
        // The seed file is copied next to the assembly (see StockPilot.Api.csproj),
        // so resolving from the app base directory works under `dotnet run`, a
        // published build, and Docker alike — regardless of the working directory.
        _filePath = Path.Combine(AppContext.BaseDirectory, "Data", "gpw-companies.json");
        _logger = logger;
    }

    public async Task<IReadOnlyList<GpwCompany>> GetCompaniesAsync(CancellationToken cancellationToken = default)
    {
        if (_companies is not null)
        {
            return _companies;
        }

        await _gate.WaitAsync(cancellationToken);
        try
        {
            // Double-check after acquiring the lock in case another caller loaded it first.
            if (_companies is not null)
            {
                return _companies;
            }

            if (!File.Exists(_filePath))
            {
                throw new FileNotFoundException($"GPW company list not found at '{_filePath}'.", _filePath);
            }

            await using var stream = File.OpenRead(_filePath);
            var companies = await JsonSerializer.DeserializeAsync<List<GpwCompany>>(stream, JsonOptions, cancellationToken)
                ?? [];

            _companies = companies.AsReadOnly();
            _logger.LogInformation("Loaded {Count} GPW companies from {Path}.", _companies.Count, _filePath);
            return _companies;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<GpwCompany?> FindAsync(string ticker, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(ticker))
        {
            return null;
        }

        var companies = await GetCompaniesAsync(cancellationToken);
        return companies.FirstOrDefault(c => string.Equals(c.Ticker, ticker, StringComparison.OrdinalIgnoreCase));
    }
}
