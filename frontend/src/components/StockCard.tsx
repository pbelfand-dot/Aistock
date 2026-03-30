import React from 'react'

export interface StockRecommendation {
  ticker: string
  company_name: string
  recommendation: 'BUY' | 'HOLD' | 'SELL'
  confidence: number
  reasoning: string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
  target_price: number
  current_price: number
  month_change_pct: number
  market_cap: string
  volume: number
  pe_ratio: number
  fifty_two_week_high: number
  fifty_two_week_low: number
}

interface StockCardProps {
  stock: StockRecommendation
  onClick: (ticker: string) => void
  index: number
}

const recommendationConfig = {
  BUY: {
    bg: 'bg-emerald-500/15',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    badge: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
    glow: 'hover:shadow-emerald-500/10',
    bar: 'bg-emerald-500',
  },
  HOLD: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    text: 'text-amber-400',
    badge: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
    glow: 'hover:shadow-amber-500/10',
    bar: 'bg-amber-500',
  },
  SELL: {
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/20',
    text: 'text-rose-400',
    badge: 'bg-rose-500/20 text-rose-300 border border-rose-500/30',
    glow: 'hover:shadow-rose-500/10',
    bar: 'bg-rose-500',
  },
}

const riskConfig = {
  LOW: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25',
  MEDIUM: 'bg-amber-500/15 text-amber-400 border border-amber-500/25',
  HIGH: 'bg-rose-500/15 text-rose-400 border border-rose-500/25',
}

const StockCard: React.FC<StockCardProps> = ({ stock, onClick, index }) => {
  const config = recommendationConfig[stock.recommendation] || recommendationConfig.HOLD
  const isPositiveChange = stock.month_change_pct >= 0
  const priceVs52wHigh = stock.fifty_two_week_high > 0
    ? ((stock.current_price - stock.fifty_two_week_low) / (stock.fifty_two_week_high - stock.fifty_two_week_low)) * 100
    : 50

  return (
    <div
      className={`stock-card cursor-pointer rounded-2xl border bg-dark-700/60 backdrop-blur-sm p-5 animate-slide-up ${config.border} hover:border-opacity-60 transition-all duration-300`}
      style={{ animationDelay: `${index * 80}ms` }}
      onClick={() => onClick(stock.ticker)}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center font-bold text-sm font-mono ${config.bg} ${config.text} border ${config.border}`}>
            {stock.ticker.slice(0, 2)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-white font-mono tracking-wide">
                {stock.ticker}
              </span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${config.badge}`}>
                {stock.recommendation}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5 truncate max-w-[140px]">
              {stock.company_name}
            </p>
          </div>
        </div>

        <div className="text-right">
          <div className="text-lg font-bold text-white font-num">
            ${stock.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className={`text-xs font-semibold font-num ${isPositiveChange ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isPositiveChange ? '▲' : '▼'} {Math.abs(stock.month_change_pct).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-xs text-slate-500">AI Confidence</span>
          <span className={`text-xs font-bold font-num ${config.text}`}>{stock.confidence}%</span>
        </div>
        <div className="h-1.5 bg-dark-500 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full progress-bar ${config.bar}`}
            style={{ width: `${stock.confidence}%` }}
          />
        </div>
      </div>

      {/* 52-week range */}
      {stock.fifty_two_week_high > 0 && (
        <div className="mb-4">
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-500 font-num">${stock.fifty_two_week_low.toFixed(0)}</span>
            <span className="text-xs text-slate-600">52-week range</span>
            <span className="text-xs text-slate-500 font-num">${stock.fifty_two_week_high.toFixed(0)}</span>
          </div>
          <div className="h-1 bg-dark-500 rounded-full relative">
            <div
              className="absolute top-0 h-full w-1 bg-brand-green rounded-full transform -translate-x-1/2 shadow-sm shadow-brand-green/50"
              style={{ left: `${Math.max(2, Math.min(98, priceVs52wHigh))}%` }}
            />
            <div className="h-full w-full rounded-full bg-gradient-to-r from-rose-500/30 via-amber-500/30 to-emerald-500/30" />
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-dark-600/50 rounded-lg px-2.5 py-2">
          <div className="text-xs text-slate-500 mb-0.5">Target Price</div>
          <div className="text-sm font-bold text-brand-green font-num">
            ${stock.target_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="bg-dark-600/50 rounded-lg px-2.5 py-2">
          <div className="text-xs text-slate-500 mb-0.5">P/E Ratio</div>
          <div className="text-sm font-bold text-slate-300 font-num">
            {stock.pe_ratio > 0 ? stock.pe_ratio.toFixed(1) : 'N/A'}
          </div>
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-xs text-slate-400 leading-relaxed line-clamp-2 mb-3">
        {stock.reasoning}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-dark-400/30">
        <span className={`text-xs px-2 py-0.5 rounded-md font-medium ${riskConfig[stock.risk_level]}`}>
          {stock.risk_level} RISK
        </span>
        <button className="flex items-center gap-1 text-xs text-brand-green hover:text-brand-green-light transition-colors">
          <span>Deep Analysis</span>
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default StockCard
