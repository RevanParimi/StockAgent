using Microsoft.EntityFrameworkCore;
using StockAgent.Scheduler.Models;

namespace StockAgent.Scheduler.Data;

public sealed class SchedulerDbContext : DbContext
{
    public SchedulerDbContext(DbContextOptions<SchedulerDbContext> options) : base(options) { }

    public DbSet<ScoreRecord> ScoreRecords => Set<ScoreRecord>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<ScoreRecord>(e =>
        {
            e.ToTable("ScoreRecords");
            e.HasIndex(r => new { r.Ticker, r.RunAt });
            e.Property(r => r.FinalScore).HasPrecision(5, 4);
            e.Property(r => r.ReportJson).HasColumnType("nvarchar(max)");
            e.Property(r => r.InvestmentThesis).HasColumnType("nvarchar(max)");
        });
    }
}
