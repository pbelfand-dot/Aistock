import React, { useState, useEffect, useRef } from 'react'
import type { StockRecommendation } from './StockCard'

interface StockAnalysisProps {
  ticker: string
  stockData?: StockRecommendation
  onClose: () => void
}

const StockAnalysis: React.FC<StockAnalysisProps> = ({ ticker, stockData, onClose }) => {
  const [analysisText, setAnalysisText] = useState('')
  const [isStreaming, setIsStreaming] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    abortRef.current = controller

    const streamAnalysis = async () => {
      try {
        setAnalysisText('')
        setIsStreaming(true)
        setError(null)

        const response = await fetch(`/api/stock/${ticker}`, {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        if (!response.body) {
          throw new Error('No response body')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          setAnalysisText(prev => prev + chunk)

          // Auto-scroll to bottom
          if (contentRef.current) {
            contentRef.current.scrollTop = contentRef.current.scrollHeight
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError((err as Error).message || 'Failed to load analysis')
        }
      } finally {
        setIsStreaming(false)
      }
    }

    streamAnalysis()

    return () => {
      controller.abort()
    }
  }, [ticker])

  const handleClose = () => {
    abortRef.current?.abort()
    onClose()
  }

  // Format markdown-like text to HTML display
  const formatAnalysisText = (text: string) => {
    const lines = text.split('\n')
    return lines.map((line, i) => {
      if (line.startsWith('### ')) {
        return (
          <h3 key={i} className="text-brand-green font-semibold text-base mt-5 mb-2 first:mt-0">
            {line.replace('### ', '')}
          </h3>
        )
      }
      if (line.startsWith('## ')) {
        return (
          <h2 key={i} className="text-white font-bold text-lg mt-6 mb-3 first:mt-0">
            {line.replace('## ', '')}
          </h2>
        )
      }
      if (line.startsWith('**') && line.endsWith('**')) {
        return (
          <p key={i} className="text-slate-200 font-semibold mt-3 mb-1">
            {line.replace(/\*\*/g, '')}
          </p>
        )
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return (
          <li key={i} className="text-slate-300 text-sm ml-4 mb-1 list-disc">
            {formatInlineText(line.replace(/^[-*] /, ''))}
          </li>
        )
      }
      if (line.trim() === '') {
        return <div key={i} className="h-2" />
      }
      return (
        <p key={i} className="text-slate-300 text-sm leading-relaxed mb-1">
          {formatInlineText(line)}
        </p>
      )
    })
  }

  const formatInlineText = (text: string): React.ReactNode => {
    const parts = text.split(/(\*\*[^*]+\*\*)/g)
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>
      }
      return part
    })
  }

  const recommendationConfig = stockData ? {
    BUY: { badge: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' },
    HOLD: { badge: 'bg-amber-500/20 text-amber-300 border border-amber-500/30' },
    SELL: { badge: 'bg-rose-500/20 text-rose-300 border border-rose-500/30' },
  }[stockData.recommendation] : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 modal-backdrop bg-dark-900/80"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border border-dark-400/50 bg-dark-800/95 shadow-2xl animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-dark-400/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-green/10 border border-brand-green/20 flex items-center justify-center">
              <span className="text-brand-green font-bold text-sm font-mono">{ticker.slice(0, 2)}</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">{ticker}</h2>
                {stockData && recommendationConfig && (
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${recommendationConfig.badge}`}>
                    {stockData.recommendation}
                  </span>
                )}
              </div>
              {stockData && (
                <p className="text-xs text-slate-500">{stockData.company_name}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Stats badges */}
            {stockData && (
              <div className="hidden sm:flex items-center gap-2">
                <div className="text-right">
                  <div className="text-base font-bold text-white font-num">
                    ${stockData.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div className={`text-xs font-num ${stockData.month_change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {stockData.month_change_pct >= 0 ? '▲' : '▼'} {Math.abs(stockData.month_change_pct).toFixed(2)}%
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={handleClose}
              className="w-8 h-8 rounded-lg bg-dark-600/60 hover:bg-dark-500/80 flex items-center justify-center text-slate-400 hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Streaming status bar */}
        {isStreaming && (
          <div className="flex items-center gap-2 px-5 py-2.5 bg-brand-green/5 border-b border-brand-green/10">
            <div className="w-3 h-3 rounded-full border-2 border-transparent border-t-brand-green animate-spin" />
            <span className="text-xs text-brand-green/80">Claude Opus 4.6 is analyzing {ticker}...</span>
          </div>
        )}

        {/* Content */}
        <div
          ref={contentRef}
          className="flex-1 overflow-y-auto p-5"
        >
          {error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-3">
                <svg className="w-6 h-6 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.07 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <p className="text-rose-400 font-medium text-sm">{error}</p>
              <p className="text-slate-500 text-xs mt-1">Please check your API key and try again</p>
            </div>
          ) : analysisText ? (
            <div className={isStreaming ? 'streaming-cursor' : ''}>
              {formatAnalysisText(analysisText)}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-12 h-12 rounded-full spinner mb-4" />
              <p className="text-slate-400 text-sm">Loading analysis...</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-dark-400/40 bg-dark-700/40">
          <div className="flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-brand-green" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span className="text-xs text-slate-500">
              Powered by Claude Opus 4.6 · For informational purposes only
            </span>
          </div>
          {!isStreaming && (
            <span className="text-xs text-emerald-500/70 flex items-center gap-1">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Complete
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default StockAnalysis
