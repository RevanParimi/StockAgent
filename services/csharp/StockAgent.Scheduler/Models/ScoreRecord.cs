using System.ComponentModel.DataAnnotations;
using System.Text.Json;

namespace StockAgent.Scheduler.Models;

/// <summary>
/// EF Core entity — one row per pipeline run, stored in SQL Server via SchedulerDbContext.
/// </summary>
public sealed class ScoreRecord
{
    [Key]
    public int Id { get; set; }

    [Required, MaxLength(20)]
    public string Ticker { get; set; } = string.Empty;

    [Required, MaxLength(200)]
    public string CompanyName { get; set; } = string.Empty;

    public DateTime RunAt { get; set; } = DateTime.UtcNow;

    public double FinalScore { get; set; }

    [Required, MaxLength(20)]
    public string Verdict { get; set; } = string.Empty;

    public string InvestmentThesis { get; set; } = string.Empty;

    /// <summary>Full report serialised as JSON for audit trail.</summary>
    public string ReportJson { get; set; } = string.Empty;

    public static ScoreRecord FromDto(FinalReportDto dto) => new()
    {
        Ticker          = dto.Ticker,
        CompanyName     = dto.CompanyName,
        FinalScore      = dto.FinalScore,
        Verdict         = dto.Verdict,
        InvestmentThesis = dto.InvestmentThesis,
        RunAt           = DateTime.UtcNow,
        ReportJson      = JsonSerializer.Serialize(dto),
    };
}
