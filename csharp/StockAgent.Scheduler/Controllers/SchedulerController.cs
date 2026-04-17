using Microsoft.AspNetCore.Mvc;
using Quartz;
using StockAgent.Scheduler.Models;

namespace StockAgent.Scheduler.Controllers;

[ApiController]
[Route("scheduler")]
public sealed class SchedulerController : ControllerBase
{
    private readonly ISchedulerFactory _schedulerFactory;
    private readonly IConfiguration _config;

    public SchedulerController(ISchedulerFactory schedulerFactory, IConfiguration config)
    {
        _schedulerFactory = schedulerFactory;
        _config = config;
    }

    /// <summary>GET /scheduler/status — queried by TypeScript dashboard (GET /api/schedule).</summary>
    [HttpGet("status")]
    public async Task<IActionResult> Status()
    {
        var scheduler = await _schedulerFactory.GetScheduler();
        var tickers   = _config.GetSection("Scheduler:Tickers").Get<List<string>>() ?? new();
        var cron      = _config["Scheduler:CronExpression"] ?? "0 30 8 ? * MON-FRI";

        var jobKeys = await scheduler.GetJobKeys(Quartz.Impl.Matchers.GroupMatcher<JobKey>.AnyGroup());
        DateTimeOffset? nextFire = null;
        foreach (var key in jobKeys)
        {
            var triggers = await scheduler.GetTriggersOfJob(key);
            var t = triggers.Select(tr => tr.GetNextFireTimeUtc()).Where(t => t.HasValue).Min();
            if (t.HasValue && (nextFire is null || t < nextFire)) nextFire = t;
        }

        return Ok(new SchedulerStatus
        {
            Enabled  = true,
            Cron     = cron,
            Tickers  = tickers,
            NextFire = nextFire?.ToString("o"),
        });
    }
}
