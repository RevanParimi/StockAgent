using System.Text.Json.Serialization;

namespace StockAgent.Scheduler.Models;

public sealed class SchedulerStatus
{
    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; }

    [JsonPropertyName("cron")]
    public string Cron { get; set; } = string.Empty;

    [JsonPropertyName("tickers")]
    public List<string> Tickers { get; set; } = new();

    [JsonPropertyName("next_fire")]
    public string? NextFire { get; set; }

    [JsonPropertyName("last_run")]
    public string? LastRun { get; set; }
}
