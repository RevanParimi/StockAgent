using Microsoft.EntityFrameworkCore;
using Quartz;
using StockAgent.Scheduler.Data;
using StockAgent.Scheduler.Models;
using System.Net.Http.Json;

namespace StockAgent.Scheduler.Jobs;

/// <summary>
/// Quartz.NET job — fires on cron "0 30 8 ? * MON-FRI" (8:30am IST weekdays).
/// For each configured ticker:
///   1. POST http://localhost:8000/analyse
///   2. Deserialise FinalReportDto
///   3. Persist to SQL Server via EF Core
///   4. Fire webhook alert when score delta ≥ threshold
/// </summary>
[DisallowConcurrentExecution]
public sealed class AnalyseJob : IJob
{
    private readonly IHttpClientFactory _httpFactory;
    private readonly SchedulerDbContext _db;
    private readonly IConfiguration _config;
    private readonly ILogger<AnalyseJob> _logger;

    public AnalyseJob(
        IHttpClientFactory httpFactory,
        SchedulerDbContext db,
        IConfiguration config,
        ILogger<AnalyseJob> logger)
    {
        _httpFactory = httpFactory;
        _db = db;
        _config = config;
        _logger = logger;
    }

    public async Task Execute(IJobExecutionContext context)
    {
        var tickers = _config.GetSection("Scheduler:Tickers").Get<List<string>>()
                      ?? new List<string> { "MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO" };

        var pythonUrl = _config["Scheduler:PythonApiUrl"] ?? "http://localhost:8000";
        var alertThreshold = _config.GetValue<double>("Scheduler:AlertScoreDeltaThreshold", 0.10);
        var webhookUrl = _config["Scheduler:WebhookUrl"] ?? string.Empty;

        foreach (var ticker in tickers)
        {
            try
            {
                await AnalyseTicker(ticker, pythonUrl, alertThreshold, webhookUrl, context.CancellationToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[AnalyseJob] Failed for ticker {Ticker}", ticker);
            }
        }
    }

    private async Task AnalyseTicker(
        string ticker, string pythonUrl, double alertThreshold,
        string webhookUrl, CancellationToken ct)
    {
        _logger.LogInformation("[AnalyseJob] Analysing {Ticker}…", ticker);

        var http = _httpFactory.CreateClient("PythonApi");
        var response = await http.PostAsJsonAsync($"{pythonUrl}/analyse", new { ticker }, ct);
        response.EnsureSuccessStatusCode();

        var dto = await response.Content.ReadFromJsonAsync<FinalReportDto>(cancellationToken: ct)
                  ?? throw new InvalidOperationException("Empty response from Python API");

        var record = ScoreRecord.FromDto(dto);
        _db.ScoreRecords.Add(record);
        await _db.SaveChangesAsync(ct);

        _logger.LogInformation(
            "[AnalyseJob] {Ticker}: score={Score:F3} verdict={Verdict}",
            ticker, dto.FinalScore, dto.Verdict);

        await CheckAndFireAlert(ticker, dto, alertThreshold, webhookUrl, ct);
    }

    private async Task CheckAndFireAlert(
        string ticker, FinalReportDto latest, double threshold,
        string webhookUrl, CancellationToken ct)
    {
        var previous = await _db.ScoreRecords
            .Where(r => r.Ticker == ticker)
            .OrderByDescending(r => r.RunAt)
            .Skip(1)   // skip the one we just inserted
            .FirstOrDefaultAsync(ct);

        if (previous is null) return;

        var delta = Math.Abs(latest.FinalScore - previous.FinalScore);
        var verdictChanged = latest.Verdict != previous.Verdict;

        if (delta < threshold && !verdictChanged) return;

        _logger.LogWarning(
            "[AnalyseJob] ALERT {Ticker}: delta={Delta:F3} verdict {Prev}→{New}",
            ticker, delta, previous.Verdict, latest.Verdict);

        if (!string.IsNullOrWhiteSpace(webhookUrl))
        {
            try
            {
                var http = _httpFactory.CreateClient();
                await http.PostAsJsonAsync(webhookUrl, new
                {
                    ticker,
                    score     = latest.FinalScore,
                    verdict   = latest.Verdict,
                    prev_score    = previous.FinalScore,
                    prev_verdict  = previous.Verdict,
                    delta,
                    verdict_changed = verdictChanged,
                }, ct);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[AnalyseJob] Webhook delivery failed for {Ticker}", ticker);
            }
        }
    }
}
