import React from 'react'

interface HeaderProps {
  onRefreshTrending: () => void
}

const Header: React.FC<HeaderProps> = ({ onRefreshTrending }) => {
  return (
    <header className="relative border-b border-dark-400/50 bg-dark-800/80 backdrop-blur-md sticky top-0 z-40">
      <div className="absolute inset-0 bg-gradient-to-r from-brand-green/5 via-transparent to-brand-green/5 pointer-events-none" />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3">
            <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-brand-green to-brand-green-dark flex items-center justify-center shadow-lg glow-green">
              <svg className="w-5 h-5 text-dark-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-brand-green rounded-full animate-pulse-slow" />
            </div>
            <div>
              <h1 className="text-xl font-bold gradient-text tracking-tight leading-none">
                AiStock
              </h1>
              <p className="text-xs text-slate-500 mt-0.5 leading-none">
                AI-Powered Investment Suggestions
              </p>
            </div>
          </div>

          {/* Center status indicator */}
          <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-dark-600/60 border border-dark-400/40">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
            <span className="text-xs text-slate-400 font-medium">Live Market Data</span>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={onRefreshTrending}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-slate-400 hover:text-brand-green border border-dark-400/40 hover:border-brand-green/30 bg-dark-600/40 hover:bg-dark-500/40 transition-all duration-200 text-sm"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span className="hidden sm:inline">Refresh</span>
            </button>

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-green/10 border border-brand-green/20">
              <svg className="w-3.5 h-3.5 text-brand-green" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <span className="text-xs text-brand-green font-semibold">Claude Opus 4.6</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}

export default Header
