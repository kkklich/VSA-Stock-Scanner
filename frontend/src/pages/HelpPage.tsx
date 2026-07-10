import { BookOpen, BarChart3, Star, Settings, Zap, Info } from 'lucide-react'

export function HelpPage() {
  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-6">
        <BookOpen size={28} className="text-emerald-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            How to use StockPilot
          </h1>
          <p className="text-sm text-slate-400">
            A Volume Spread Analysis scanner for the Warsaw Stock Exchange
          </p>
        </div>
      </div>

      {/* Quick navigation */}
      <div className="grid gap-2 sm:grid-cols-2">
        <a
          href="#dashboard"
          className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-emerald-400 hover:bg-slate-800"
        >
          <BarChart3 size={16} />
          Dashboard & Ranking
        </a>
        <a
          href="#watchlist"
          className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-emerald-400 hover:bg-slate-800"
        >
          <Star size={16} />
          Watchlist
        </a>
        <a
          href="#scanner"
          className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-emerald-400 hover:bg-slate-800"
        >
          <Zap size={16} />
          VSA Scanner
        </a>
        <a
          href="#charts"
          className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-emerald-400 hover:bg-slate-800"
        >
          <BarChart3 size={16} />
          Stock Charts
        </a>
      </div>

      {/* Main content sections */}
      <div className="space-y-8">
        {/* Section 1: Dashboard */}
        <section id="dashboard" className="space-y-4">
          <div className="flex items-center gap-2">
            <BarChart3
              size={24}
              className="text-emerald-500"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              Dashboard & Stock Ranking
            </h2>
          </div>

          <div className="space-y-3 text-sm text-slate-300">
            <p>
              The <span className="font-semibold text-slate-200">Dashboard</span>{' '}
              is your main view, showing GPW stocks ranked by VSA Rating
              (0–100). This score measures the quality of volume-spread patterns
              that indicate professional trading activity.
            </p>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">View Options:</h3>
              <ul className="space-y-2">
                <li>
                  <span className="font-medium text-emerald-400">Best VSA</span>
                  {' — '}Highest-rated stocks today (recommended for swing traders)
                </li>
                <li>
                  <span className="font-medium text-emerald-400">Winners</span>
                  {' — '}Largest price gainers in the session
                </li>
                <li>
                  <span className="font-medium text-emerald-400">Losers</span>
                  {' — '}Largest price losers in the session
                </li>
                <li>
                  <span className="font-medium text-emerald-400">Favorites</span>
                  {' — '}Your starred stocks, ranked by VSA rating
                </li>
              </ul>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">Reading the ratings:</h3>
              <ul className="space-y-2 text-xs text-slate-400">
                <li>
                  <span className="inline-block rounded bg-emerald-600 px-2 py-1 font-semibold text-white">
                    &gt;70
                  </span>
                  {' Strong bullish setup — professional accumulation'}
                </li>
                <li>
                  <span className="inline-block rounded bg-slate-600 px-2 py-1 font-semibold text-white">
                    30–70
                  </span>
                  {' Neutral — mixed signals or consolidation'}
                </li>
                <li>
                  <span className="inline-block rounded bg-rose-600 px-2 py-1 font-semibold text-white">
                    &lt;30
                  </span>
                  {' Bearish setup — professional distribution'}
                </li>
              </ul>
            </div>

            <p>
              Click any stock to open its interactive chart and detailed metrics.
              Use the{' '}
              <Star size={13} className="inline text-amber-400 fill-amber-400" />
              {' '}star icon to add stocks to your Watchlist.
            </p>
          </div>
        </section>

        {/* Section 2: Watchlist */}
        <section id="watchlist" className="space-y-4">
          <div className="flex items-center gap-2">
            <Star
              size={24}
              className="text-amber-400"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              Watchlist
            </h2>
          </div>

          <div className="space-y-3 text-sm text-slate-300">
            <p>
              Your <span className="font-semibold text-slate-200">Watchlist</span>{' '}
              is a personal collection of stocks you want to monitor. Add stocks
              by clicking the star icon (
              <Star size={13} className="inline text-slate-400" />
              ) on any stock in the Dashboard or Scanner.
            </p>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">Features:</h3>
              <ul className="space-y-2 list-disc list-inside text-slate-400">
                <li>All starred stocks automatically appear in the Watchlist</li>
                <li>
                  Sortable by any column — click a header to sort (rating,
                  price, signal, …)
                </li>
                <li>Persisted in your browser — stays across sessions</li>
                <li>Quick way to check your favorite stocks</li>
              </ul>
            </div>

            <p className="text-slate-400">
              The Watchlist is saved locally in your browser. Clearing your
              browser data will reset your list.
            </p>
          </div>
        </section>

        {/* Section 3: Scanner */}
        <section id="scanner" className="space-y-4">
          <div className="flex items-center gap-2">
            <Zap
              size={24}
              className="text-yellow-500"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              VSA Scanner & Settings
            </h2>
          </div>

          <div className="space-y-3 text-sm text-slate-300">
            <p>
              The <span className="font-semibold text-slate-200">Scanner</span>{' '}
              page lets you customize VSA signal detection. This is where you
              fine-tune the engine to match your trading style.
            </p>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">Available Signals:</h3>
              <ul className="space-y-2">
                <li>
                  <span className="font-medium text-emerald-400">Spring</span>
                  {' — '}Professional buying before a rally; trend reversal signal
                </li>
                <li>
                  <span className="font-medium text-rose-400">Upthrust</span>
                  {' — '}Professional distribution attempt; caution signal
                </li>
                <li>
                  <span className="font-medium text-emerald-400">Test</span>
                  {' — '}Re-testing support; continuation signal
                </li>
                <li>
                  <span className="font-medium text-emerald-400">SOS</span>
                  {' — '}Sign Of Strength; bullish continuation
                </li>
                <li>
                  <span className="font-medium text-rose-400">SOW</span>
                  {' — '}Sign Of Weakness; bearish continuation
                </li>
                <li>
                  <span className="font-medium text-rose-400">No Demand</span>
                  {' — '}Low volume at higher prices; potential weakness
                </li>
              </ul>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">
                How to use:
              </h3>
              <ol className="space-y-2 list-decimal list-inside text-slate-400">
                <li>Toggle each signal on/off based on what interests you</li>
                <li>Adjust sensitivity sliders (0–100) for stricter/looser detection</li>
                <li>The Dashboard and Charts instantly update to reflect your settings</li>
                <li>
                  Try different combinations and watch how the rankings change
                </li>
              </ol>
            </div>

            <p className="text-slate-400">
              Settings are saved in your browser and persist across sessions.
              They are sent with every API request, so all pages always reflect
              them. Clearing your browser data resets them to defaults.
            </p>
          </div>
        </section>

        {/* Section 4: Stock Charts */}
        <section id="charts" className="space-y-4">
          <div className="flex items-center gap-2">
            <BarChart3
              size={24}
              className="text-blue-500"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              Stock Charts & Details
            </h2>
          </div>

          <div className="space-y-3 text-sm text-slate-300">
            <p>
              Click any stock from the Dashboard or Watchlist to open its
              interactive candlestick chart with VSA signal overlays.
            </p>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">What you see:</h3>
              <ul className="space-y-2">
                <li>
                  <span className="font-medium">Candlestick chart</span>
                  {' — '}12 months of daily bars (zoom & scroll to explore)
                </li>
                <li>
                  <span className="font-medium">VSA signal markers</span>
                  {' — '}Visual flags showing Spring, Upthrust, Test, etc.
                </li>
                <li>
                  <span className="font-medium">Company fundamentals</span>
                  {' — '}Market cap, P/E ratio, EPS, dividend yield
                </li>
                <li>
                  <span className="font-medium">Price metrics</span>
                  {' — '}Current price, daily change, volume
                </li>
              </ul>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">
                Chart controls:
              </h3>
              <ul className="space-y-2 text-slate-400">
                <li>
                  <span className="font-mono text-xs bg-slate-800 px-2 py-1 rounded">
                    Scroll
                  </span>
                  {' Navigate through time'}
                </li>
                <li>
                  <span className="font-mono text-xs bg-slate-800 px-2 py-1 rounded">
                    Pinch/Scroll
                  </span>
                  {' Zoom in & out'}
                </li>
                <li>
                  <span className="font-mono text-xs bg-slate-800 px-2 py-1 rounded">
                    Click
                  </span>
                  {' Select a candle for details'}
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* Section 5: VSA Basics */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Info
              size={24}
              className="text-slate-400"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              What is Volume Spread Analysis?
            </h2>
          </div>

          <div className="space-y-3 text-sm text-slate-300">
            <p>
              Volume Spread Analysis (VSA) is a price-action method developed by
              Tom Williams that interprets the relationship between{' '}
              <span className="font-semibold">spread</span> (high − low),{' '}
              <span className="font-semibold">close position</span> (where the bar
              closed within the range), and{' '}
              <span className="font-semibold">volume</span> to identify
              professional trading activity.
            </p>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">
                Core principle:
              </h3>
              <p className="text-slate-400">
                Professional traders (the "smart money") leave footprints in the
                volume-spread relationship. A Spring (a dip below support that
                closes back above it, near the high — sellers trapped) often
                precedes a rally. An Upthrust (a spike above resistance that
                closes back below it, near the low — buyers trapped) can signal
                weakness after the bar. StockPilot detects these patterns
                automatically.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="font-semibold text-slate-100">
                Why use VSA?
              </h3>
              <ul className="space-y-2 list-disc list-inside text-slate-400">
                <li>Filter out noise — focus on bars with structure</li>
                <li>
                  Spot reversals early — before price confirmation
                </li>
                <li>
                  Trade with the pros — ride moves started by smart money
                </li>
                <li>Works on any timeframe and any liquid stock</li>
              </ul>
            </div>

            <p className="text-slate-400 italic">
              For deeper learning, search "Volume Spread Analysis Tom Williams"
              or "VSA trading" to find tutorials, books, and research.
            </p>
          </div>
        </section>

        {/* Section 6: Tips & Tricks */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Settings
              size={24}
              className="text-slate-400"
              strokeWidth={1.5}
            />
            <h2 className="text-xl font-bold text-slate-100">
              Tips & Frequently Asked
            </h2>
          </div>

          <div className="space-y-4 text-sm text-slate-300">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: How often is data updated?
              </h4>
              <p className="text-slate-400">
                Once daily after the Warsaw Stock Exchange closes (EOD). Rankings
                and signals are recomputed nightly.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: Can I use this for intraday trading?
              </h4>
              <p className="text-slate-400">
                Currently, StockPilot works with daily (EOD) data. Intraday
                (15-min, 1-hour bars) support is on the roadmap.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: What's the minimum stock price or volume?
              </h4>
              <p className="text-slate-400">
                StockPilot only ranks stocks with a 20-session median turnover
                &gt; 100,000 PLN and market cap &gt; 100M PLN. This filters out
                low-liquidity stocks where VSA is unreliable.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: My Watchlist disappeared. Why?
              </h4>
              <p className="text-slate-400">
                Your Watchlist is stored in your browser's local storage. If you
                clear your browser data or use a private window, it will reset.
                Future versions will sync to an account.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: Can I export data?
              </h4>
              <p className="text-slate-400">
                Yes — on the Watchlist page, the Export button downloads a CSV
                file of the current view (with your filters, search and sorting
                applied). API access is a planned feature.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: Is there a mobile app?
              </h4>
              <p className="text-slate-400">
                StockPilot is a responsive web app — it works on phones and
                tablets in your browser. A native mobile app is not planned yet.
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
              <h4 className="font-semibold text-emerald-400">
                Q: How do I report a bug or suggest a feature?
              </h4>
              <p className="text-slate-400">
                Contact support or use the feedback form (coming soon). For now,
                reach out via email with details.
              </p>
            </div>
          </div>
        </section>

        {/* Footer */}
        <div className="border-t border-slate-800 pt-6 text-xs text-slate-500">
          <p>
            <strong>Disclaimer:</strong> StockPilot is a screening and analysis
            tool only. It is not financial advice. Always do your own research,
            manage risk, and consult a licensed advisor before trading. Past
            performance does not guarantee future results.
          </p>
        </div>
      </div>
    </div>
  )
}
