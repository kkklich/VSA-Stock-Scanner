using System.Net;
using StockPilot.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// CORS policy for the React frontend (Vite dev server defaults to 5173).
const string FrontendCorsPolicy = "FrontendCorsPolicy";
var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? new[] { "http://localhost:5173" };

builder.Services.AddCors(options =>
{
    options.AddPolicy(FrontendCorsPolicy, policy =>
        policy.WithOrigins(allowedOrigins)
            .AllowAnyHeader()
            .AllowAnyMethod());
});

// Add services to the container.
builder.Services.AddControllers();
// Learn more about configuring OpenAPI at https://aka.ms/aspnet/openapi
builder.Services.AddOpenApi();

// In-memory cache for daily-refreshing market data (see DOCUMENTATION.md §5).
builder.Services.AddMemoryCache();

// Tracked GPW company list (loaded once from Data/gpw-companies.json).
builder.Services.AddSingleton<IGpwCompanyService, GpwCompanyService>();

// Typed HttpClient for stooq.pl. A shared CookieContainer keeps the anti-bot
// auth cookie across calls, and a browser-like User-Agent avoids trivial blocks.
builder.Services.AddHttpClient<IStooqClient, StooqClient>(client =>
    {
        client.Timeout = TimeSpan.FromSeconds(30);
        client.DefaultRequestHeaders.UserAgent.ParseAdd(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36");
    })
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
    {
        CookieContainer = new CookieContainer(),
        UseCookies = true,
        AutomaticDecompression = DecompressionMethods.All,
    })
    .SetHandlerLifetime(TimeSpan.FromMinutes(10));

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseHttpsRedirection();

app.UseCors(FrontendCorsPolicy);

app.UseAuthorization();

app.MapControllers();

app.Run();
