using Microsoft.EntityFrameworkCore;
using Quartz;
using StockAgent.Scheduler.Data;
using StockAgent.Scheduler.Jobs;

var builder = WebApplication.CreateBuilder(args);

// ---------------------------------------------------------------------------
// EF Core — SQL Server
// ---------------------------------------------------------------------------
builder.Services.AddDbContext<SchedulerDbContext>(options =>
    options.UseSqlServer(builder.Configuration.GetConnectionString("DefaultConnection")));

// ---------------------------------------------------------------------------
// HTTP client with Polly retry (calls Python FastAPI)
// ---------------------------------------------------------------------------
builder.Services.AddHttpClient("PythonApi")
    .AddTransientHttpErrorPolicy(p =>
        p.WaitAndRetryAsync(3, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt))));

// ---------------------------------------------------------------------------
// Quartz.NET — cron job: 0 30 8 ? * MON-FRI  (8:30am IST weekdays)
// ---------------------------------------------------------------------------
builder.Services.AddQuartz(q =>
{
    var cron = builder.Configuration["Scheduler:CronExpression"] ?? "0 30 8 ? * MON-FRI";

    q.AddJob<AnalyseJob>(j => j.WithIdentity("analyse-job"));
    q.AddTrigger(t => t
        .ForJob("analyse-job")
        .WithIdentity("analyse-trigger")
        .WithCronSchedule(cron, s => s.InTimeZone(TimeZoneInfo.FindSystemTimeZoneById("India Standard Time")))
    );
});

builder.Services.AddQuartzHostedService(opt => opt.WaitForJobsToComplete = true);

// ---------------------------------------------------------------------------
// ASP.NET Core — port 5000
// ---------------------------------------------------------------------------
builder.Services.AddControllers()
    .AddJsonOptions(o =>
        o.JsonSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.SnakeCaseLower);

builder.Services.AddEndpointsApiExplorer();

var app = builder.Build();

// Apply EF Core migrations on startup
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<SchedulerDbContext>();
    db.Database.Migrate();
}

app.MapControllers();

app.Run();
