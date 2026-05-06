# ============================================================
# StockAgent — C# Quartz.NET Scheduler
# ============================================================

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder

WORKDIR /src

COPY *.csproj ./
RUN dotnet restore

COPY . ./
RUN dotnet publish -c Release -o /app/publish --no-restore

# ──────────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/publish ./

EXPOSE 5000

ENTRYPOINT ["dotnet", "StockAgent.Scheduler.dll"]
