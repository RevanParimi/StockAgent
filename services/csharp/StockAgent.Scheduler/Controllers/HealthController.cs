using Microsoft.AspNetCore.Mvc;
using Quartz;

namespace StockAgent.Scheduler.Controllers;

[ApiController]
[Route("[controller]")]
public sealed class HealthController : ControllerBase
{
    private readonly ISchedulerFactory _schedulerFactory;

    public HealthController(ISchedulerFactory schedulerFactory)
        => _schedulerFactory = schedulerFactory;

    /// <summary>GET /health — checked by TypeScript dashboard and Python migration script.</summary>
    [HttpGet]
    public async Task<IActionResult> Get()
    {
        var scheduler = await _schedulerFactory.GetScheduler();
        var nextTrigger = await GetNextFireUtc(scheduler);
        return Ok(new
        {
            status        = "ok",
            service       = "StockAgent.Scheduler",
            next_fire_utc = nextTrigger?.ToString("o"),
        });
    }

    private static async Task<DateTimeOffset?> GetNextFireUtc(IScheduler scheduler)
    {
        var jobKeys = await scheduler.GetJobKeys(Quartz.Impl.Matchers.GroupMatcher<JobKey>.AnyGroup());
        foreach (var key in jobKeys)
        {
            var triggers = await scheduler.GetTriggersOfJob(key);
            var next = triggers.Select(t => t.GetNextFireTimeUtc()).Where(t => t.HasValue).Min();
            if (next.HasValue) return next;
        }
        return null;
    }
}
