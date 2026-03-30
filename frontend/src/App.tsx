import React, { useState, useEffect } from 'react'
import Header from './components/Header'
import StockCard, { StockRecommendation } from './components/StockCard'
import StockAnalysis from './components/StockAnalysis'

interface TrendingStock {
  ticker: string
  company_name: string
  current_price: number
  month_change_pct: number
  volume: number
  market_cap: string
  sector: string
}

type AppState = 'idle' | 'loading' | 'success' | 'error'

const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>('idle')
  const [recommendations, setRecommendations] = useState<StockRecommendation[]>([])
  const [trending, setTrending] = useState<TrendingStock[]>([])
  const [trendingLoading, setTrendingLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchTrending = async () => {
    setTrendingLoading(true)
    try {
      const res = await fetch('/api/trending')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setTrending(data.trending || [])
    } catch (err) {
      console.error('Failed to fetch trending:', err)
    } finally {
      setTrendingLoading(false)
    }
  }

  const fetchSuggestions = async () => {
    setAppState('loading')
    setError(null)

    try {
      const res = await fetch('/api/suggestions')
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setRecommendations(data.recommendations || [])
      setLastUpdated(new Date())
      setAppState('success')
    } catch (err) {
      const message = (err as Error).message || 'Failed to get suggestions'
      setError(message)
      setAppState('error')
    }
  }

  const selectedStock = recommendations.find(r => r.ticker === selectedTicker)

  // Load trending on mount
  useEffect(() => {
    fetchTrending()
  }, [])

  const formatNumber = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
    return n.toString()
  }

  const buyCnt = recommendations.filter(r => r.recommendation === 'BUY').length
  const holdCnt = recommendations.filter(r => r.recommendation === 'HOLD').length
  const sellCnt = recommendations.filter(r => r.recommendation === 'SELL').length

  return (
    <div className="min-h-screen bg-dark-900">
      <Header onRefreshTrending={fetchTrending} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Hero section */}
        <div className="relative rounded-2xl border border-dark-400/40 bg-gradient-to-br from-dark-700/80 via-dark-800/60 to-dark-700/80 p-8 mb-8 overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-brand-green/5 via-transparent to-brand-green/3 pointer-events-none" />
          <div className="absolute top-0 right-0 w-64 h-64 bg-brand-green/5 rounded-full blur-3xl pointer-events-none" />

          <div className="relative flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-green bg-brand-green/10 border border-brand-green/20 px-2.5 py-1 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
                  AI-Powered Analysis
                </span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-2 leading-tight">
                Smart Stock Recommendations
                <br />
                <span className="gradient-text">Powered by Claude</span>
              </h2>
              <p className="text-slate-400 text-sm max-w-xl">
                Get real-time AI analysis of top tech stocks. Claude Opus 4.6 with adaptive thinking
                evaluates fundamentals, momentum, and risk to surface the best opportunities.
              </p>
            </div>

            <div className="flex flex-col items-center gap-3 shrink-0">
              <button
                onClick={fetchSuggestions}
                disabled={appState === 'loading'}
                className="relative group flex items-center gap-3 px-7 py-3.5 rounded-xl font-semibold text-dark-900 bg-gradient-to-r from-brand-green to-brand-green-dark hover:from-brand-green-light hover:to-brand-green disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-300 shadow-lg glow-green hover:glow-green-strong"
              >
                {appState === 'loading' ? (
                  <>
                    <div className="w-5 h-5 rounded-full border-2 border-dark-900/30 border-t-dark-900 animate-spin" />
                    <span>Analyzing Markets...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    <span>Get AI Suggestions</span>
                  </>
                )}
              </button>
              {lastUpdated && (
                <p className="text-xs text-slate-500">
                  Updated {lastUpdated.toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Loading state */}
        {appState === 'loading' && (
          <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
            <div className="relative mb-6">
              <div className="w-20 h-20 rounded-full border-2 border-brand-green/10 border-t-brand-green animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center">
                <svg className="w-8 h-8 text-brand-green/60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              </div>
            </div>
            <h3 className="text-white font-semibold text-lg mb-1">Analyzing Market Data</h3>
            <p className="text-slate-500 text-sm text-center max-w-sm">
              Fetching live stock data and running Claude Opus 4.6 analysis with adaptive thinking...
            </p>
            <div className="flex gap-1.5 mt-6">
              {['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'].map((t, i) => (
                <span
                  key={t}
                  className="text-xs px-2 py-1 rounded bg-dark-600/60 text-slate-500 font-mono animate-pulse"
                  style={{ animationDelay: `${i * 150}ms` }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Error state */}
        {appState === 'error' && (
          <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
            <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.07 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h3 className="text-white font-semibold mb-2">Analysis Failed</h3>
            <p className="text-slate-400 text-sm text-center max-w-md mb-4">{error}</p>
            <button
              onClick={fetchSuggestions}
              className="px-4 py-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 transition-colors text-sm"
            >
              Try Again
            </button>
          </div>
        )}

        {/* Recommendations grid */}
        {appState === 'success' && recommendations.length > 0 && (
          <div className="animate-fade-in">
            {/* Summary stats */}
            <div className="flex flex-wrap items-center gap-4 mb-6">
              <h3 className="text-white font-bold text-lg">AI Recommendations</h3>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  {buyCnt} BUY
                </span>
                <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  {holdCnt} HOLD
                </span>
                <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-rose-400" />
                  {sellCnt} SELL
                </span>
              </div>
              <span className="text-slate-500 text-xs ml-auto">
                Click any card for deep AI analysis
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {recommendations.map((stock, i) => (
                <StockCard
                  key={stock.ticker}
                  stock={stock}
                  index={i}
                  onClick={setSelectedTicker}
                />
              ))}
            </div>
          </div>
        )}

        {/* Idle CTA */}
        {appState === 'idle' && (
          <div className="flex flex-col items-center justify-center py-16 text-center animate-fade-in">
            <div className="relative w-20 h-20 mb-6">
              <div className="absolute inset-0 rounded-2xl bg-brand-green/10 border border-brand-green/20 flex items-center justify-center">
                <svg className="w-10 h-10 text-brand-green/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-brand-green/20 border border-brand-green/30 flex items-center justify-center animate-pulse-slow">
                <svg className="w-2.5 h-2.5 text-brand-green" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
            </div>
            <h3 className="text-white font-bold text-xl mb-2">Ready to Analyze</h3>
            <p className="text-slate-400 text-sm max-w-sm">
              Click "Get AI Suggestions" above to get Claude's analysis on AAPL, MSFT, GOOGL, AMZN, NVDA, META, and TSLA.
            </p>
          </div>
        )}

        {/* Trending section */}
        <div className="mt-12">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <h3 className="text-white font-bold text-lg">Trending Stocks</h3>
              <span className="text-xs px-2 py-0.5 rounded bg-dark-600/60 text-slate-500 border border-dark-400/40">
                Live Data
              </span>
            </div>
            {trendingLoading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <div className="w-3 h-3 rounded-full border border-transparent border-t-brand-green/60 animate-spin" />
                Loading...
              </div>
            )}
          </div>

          {trending.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {trending.map((stock) => {
                const isPos = stock.month_change_pct >= 0
                return (
                  <button
                    key={stock.ticker}
                    onClick={() => setSelectedTicker(stock.ticker)}
                    className="group text-left rounded-xl border border-dark-400/40 bg-dark-700/50 hover:bg-dark-600/60 hover:border-dark-300/40 p-4 transition-all duration-200"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="text-sm font-bold text-white font-mono">{stock.ticker}</div>
                        <div className="text-xs text-slate-500 truncate max-w-[90px] mt-0.5">{stock.company_name}</div>
                      </div>
                      <span className={`text-xs font-bold font-num px-1.5 py-0.5 rounded ${isPos ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'}`}>
                        {isPos ? '+' : ''}{stock.month_change_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="text-base font-bold text-slate-200 font-num mb-1">
                      ${stock.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-600">{stock.market_cap}</span>
                      <span className="text-xs text-slate-600">{formatNumber(stock.volume)}</span>
                    </div>

                    {/* Subtle chart bar for visual */}
                    <div className="mt-2 h-0.5 rounded-full overflow-hidden bg-dark-500">
                      <div
                        className={`h-full rounded-full ${isPos ? 'bg-emerald-500/60' : 'bg-rose-500/60'}`}
                        style={{ width: `${Math.min(100, Math.abs(stock.month_change_pct) * 5 + 20)}%` }}
                      />
                    </div>
                  </button>
                )
              })}
            </div>
          ) : !trendingLoading && (
            <div className="text-center py-8 text-slate-500 text-sm border border-dark-400/30 rounded-xl">
              No trending data available
            </div>
          )}

          {trendingLoading && trending.length === 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {Array.from({ length: 10 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-dark-400/30 bg-dark-700/40 p-4 animate-pulse">
                  <div className="h-4 bg-dark-500/60 rounded mb-2 w-14" />
                  <div className="h-3 bg-dark-500/40 rounded mb-3 w-20" />
                  <div className="h-5 bg-dark-500/60 rounded w-16" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Disclaimer */}
        <div className="mt-10 py-5 border-t border-dark-400/20 text-center">
          <p className="text-xs text-slate-600 max-w-2xl mx-auto">
            AiStock is for informational purposes only and does not constitute financial advice.
            Always conduct your own research and consult with a licensed financial advisor before making investment decisions.
            Past performance is not indicative of future results.
          </p>
        </div>
      </main>

      {/* Stock Analysis Modal */}
      {selectedTicker && (
        <StockAnalysis
          ticker={selectedTicker}
          stockData={selectedStock}
          onClose={() => setSelectedTicker(null)}
        />
      )}
    </div>
  )
}

export default App
