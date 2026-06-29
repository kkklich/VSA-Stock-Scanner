using StockPilot.Api.Models;

namespace StockPilot.Api.Services;

/// <summary>
/// Provides the list of GPW-listed companies that the scanner tracks.
/// </summary>
public interface IGpwCompanyService
{
    /// <summary>Returns every tracked GPW company.</summary>
    Task<IReadOnlyList<GpwCompany>> GetCompaniesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Finds a company by its stooq ticker (case-insensitive), or <c>null</c>
    /// if the ticker is not in the tracked list.
    /// </summary>
    Task<GpwCompany?> FindAsync(string ticker, CancellationToken cancellationToken = default);
}
