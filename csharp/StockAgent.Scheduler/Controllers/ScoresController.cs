using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using StockAgent.Scheduler.Data;
using StockAgent.Scheduler.Models;

namespace StockAgent.Scheduler.Controllers;

[ApiController]
[Route("[controller]")]
public sealed class ScoresController : ControllerBase
{
    private readonly SchedulerDbContext _db;
    private readonly ILogger<ScoresController> _logger;

    public ScoresController(SchedulerDbContext db, ILogger<ScoresController> logger)
    {
        _db = db;
        _logger = logger;
    }

    /// <summary>
    /// POST /scores — called by Python score_store.save() when CSHARP_SCHEDULER_ENABLED=true.
    /// Also used by the SQLite→SQL Server migration script.
    /// </summary>
    [HttpPost]
    public async Task<IActionResult> Create([FromBody] FinalReportDto dto)
    {
        if (!ModelState.IsValid) return BadRequest(ModelState);

        var record = ScoreRecord.FromDto(dto);
        _db.ScoreRecords.Add(record);
        await _db.SaveChangesAsync();

        _logger.LogInformation(
            "[ScoresController] Saved {Ticker} score={Score:F3} verdict={Verdict}",
            dto.Ticker, dto.FinalScore, dto.Verdict);

        return StatusCode(201, new { id = record.Id });
    }

    /// <summary>GET /scores/{ticker} — history for a ticker (newest first).</summary>
    [HttpGet("{ticker}")]
    public async Task<IActionResult> History(string ticker, [FromQuery] int limit = 30)
    {
        var rows = await _db.ScoreRecords
            .Where(r => r.Ticker == ticker.ToUpper())
            .OrderByDescending(r => r.RunAt)
            .Take(limit)
            .Select(r => new
            {
                r.Id, r.Ticker, r.CompanyName,
                run_at      = r.RunAt.ToString("o"),
                final_score = r.FinalScore,
                r.Verdict,
            })
            .ToListAsync();

        return Ok(rows);
    }

    /// <summary>GET /scores/{ticker}/latest — most recent record for a ticker.</summary>
    [HttpGet("{ticker}/latest")]
    public async Task<IActionResult> Latest(string ticker)
    {
        var row = await _db.ScoreRecords
            .Where(r => r.Ticker == ticker.ToUpper())
            .OrderByDescending(r => r.RunAt)
            .FirstOrDefaultAsync();

        return row is null ? NotFound() : Ok(row);
    }
}
