using System.Text.Json.Serialization;

namespace StockAgent.Scheduler.Models;

/// <summary>
/// Mirrors Python's FinalReport.model_dump() — snake_case keys via JsonNamingPolicy.SnakeCaseLower.
/// </summary>
public sealed class FinalReportDto
{
    [JsonPropertyName("ticker")]
    public string Ticker { get; set; } = string.Empty;

    [JsonPropertyName("company_name")]
    public string CompanyName { get; set; } = string.Empty;

    [JsonPropertyName("final_score")]
    public double FinalScore { get; set; }

    [JsonPropertyName("verdict")]
    public string Verdict { get; set; } = string.Empty;

    [JsonPropertyName("weighted_agent_scores")]
    public Dictionary<string, WeightedAgentScoreDto> WeightedAgentScores { get; set; } = new();

    [JsonPropertyName("conviction_drivers")]
    public List<string> ConvictionDrivers { get; set; } = new();

    [JsonPropertyName("top_risks")]
    public List<string> TopRisks { get; set; } = new();

    [JsonPropertyName("investment_thesis")]
    public string InvestmentThesis { get; set; } = string.Empty;

    [JsonPropertyName("report_date")]
    public string ReportDate { get; set; } = string.Empty;
}

public sealed class WeightedAgentScoreDto
{
    [JsonPropertyName("raw")]
    public double Raw { get; set; }

    [JsonPropertyName("weight")]
    public double Weight { get; set; }

    [JsonPropertyName("weighted")]
    public double Weighted { get; set; }
}
