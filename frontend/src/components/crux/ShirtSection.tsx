import React, { useState } from 'react'
import { Product, ColorVariant } from '../../data/products'

interface ShirtSectionProps {
  product: Product
}

const ShirtSection: React.FC<ShirtSectionProps> = ({ product }) => {
  const [activeColor, setActiveColor] = useState<ColorVariant>(product.colors[0])
  const [activeSize, setActiveSize] = useState('M')

  return (
    <section id={product.id} className="relative bg-[#080808] py-24 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-white/2 via-transparent to-transparent pointer-events-none" />

      <div className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          {/* Visual */}
          <div className="relative flex items-center justify-center">
            {/* All 5 color swatches stacked */}
            <div className="relative w-full max-w-sm" style={{ height: 420 }}>
              {product.colors.map((c, i) => {
                const isActive = c.id === activeColor.id
                const offset = i * 8
                return (
                  <button
                    key={c.id}
                    onClick={() => setActiveColor(c)}
                    className={`absolute transition-all duration-500 cursor-pointer`}
                    style={{
                      left: `${offset}px`,
                      top: `${offset}px`,
                      width: `calc(100% - ${product.colors.length * 8}px)`,
                      height: 380,
                      backgroundColor: c.hex,
                      zIndex: isActive ? 10 : product.colors.length - i,
                      transform: isActive ? 'scale(1.02) translateY(-8px)' : 'scale(1)',
                      boxShadow: isActive ? '0 20px 60px rgba(0,0,0,0.6)' : '0 4px 12px rgba(0,0,0,0.3)',
                      clipPath: 'polygon(6% 0%, 94% 0%, 100% 6%, 100% 94%, 94% 100%, 6% 100%, 0% 94%, 0% 6%)',
                    }}
                  >
                    {/* Shirt SVG inside each card */}
                    <div className="absolute inset-0 flex items-center justify-center p-8">
                      <ShirtSVG color={c.hex} isDark={c.accentHex === '#ffffff'} />
                    </div>
                    {/* Color label */}
                    <div
                      className="absolute bottom-4 left-4 text-[10px] tracking-[0.3em] uppercase font-bold"
                      style={{ color: c.accentHex, opacity: 0.4 }}
                    >
                      {c.name}
                    </div>
                    {/* Active ring */}
                    {isActive && (
                      <div className="absolute inset-0 ring-1 ring-white/20"
                        style={{ clipPath: 'polygon(6% 0%, 94% 0%, 100% 6%, 100% 94%, 94% 100%, 6% 100%, 0% 94%, 0% 6%)' }}
                      />
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Info */}
          <div>
            <p className="text-white/20 text-xs tracking-[0.4em] uppercase mb-3">04 / Overshirt</p>
            <h2 className="text-4xl md:text-5xl font-black text-white tracking-tight leading-none mb-2">
              {product.name}
            </h2>
            <p className="text-white/30 text-xs tracking-widest uppercase mb-8">{product.tagline}</p>

            {/* Color row */}
            <div className="flex items-center gap-3 mb-8">
              <span className="text-white/30 text-xs tracking-widest uppercase min-w-[60px]">Color</span>
              <div className="flex gap-2">
                {product.colors.map(c => (
                  <button
                    key={c.id}
                    onClick={() => setActiveColor(c)}
                    title={c.name}
                    className={`w-6 h-6 rounded-full transition-all duration-200 ${
                      c.id === activeColor.id ? 'ring-2 ring-white ring-offset-1 ring-offset-black scale-110' : ''
                    }`}
                    style={{ backgroundColor: c.hex }}
                  />
                ))}
              </div>
              <span className="text-white/50 text-xs">{activeColor.name}</span>
            </div>

            {/* Size */}
            {product.sizeChart && (
              <div className="mb-8">
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-white/30 text-xs tracking-widest uppercase min-w-[60px]">Size</span>
                  <div className="flex gap-2">
                    {product.sizeChart.rows.map(r => (
                      <button
                        key={r.size}
                        onClick={() => setActiveSize(r.size)}
                        className={`w-10 h-10 text-xs font-bold tracking-wider transition-all duration-200 ${
                          r.size === activeSize
                            ? 'bg-white text-black'
                            : 'border border-white/15 text-white/50 hover:border-white/40 hover:text-white'
                        }`}
                      >
                        {r.size}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-white/20 text-xs tracking-wider ml-[72px]">{product.sizeChart.fitNote}</p>
              </div>
            )}

            {/* Features */}
            <div className="flex flex-wrap gap-2 mb-8">
              {product.features.map(f => (
                <span
                  key={f.label}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-white/8 text-white/40 text-xs tracking-widest uppercase hover:border-white/25 hover:text-white/70 transition-all"
                >
                  <span className="text-white/20">{f.icon}</span>
                  {f.label}
                </span>
              ))}
            </div>

            {/* Materials */}
            <div className="border-t border-white/5 pt-6 mb-8">
              <p className="text-white/20 text-xs tracking-widest uppercase mb-3">Materials</p>
              {product.materials.map((m, i) => (
                <p key={i} className="text-white/40 text-xs leading-relaxed mb-1">
                  <span className="text-white/15 mr-2">—</span>{m}
                </p>
              ))}
            </div>

            {/* CTA */}
            <div className="flex gap-3">
              <button className="flex-1 py-4 bg-white text-black font-bold tracking-widest uppercase text-sm hover:bg-white/90 transition-all hover:scale-[1.01]">
                Add to Cart — {activeColor.name}
              </button>
            </div>
          </div>
        </div>

        {/* Tech breakdown grid */}
        <div className="mt-20 border-t border-white/5 pt-12">
          <p className="text-white/20 text-xs tracking-[0.4em] uppercase mb-8">Technical Breakdown</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {product.techBreakdown.map(t => (
              <div key={t.label} className="group">
                <div className="w-5 h-px bg-white/15 mb-3 group-hover:w-10 transition-all duration-300" />
                <p className="text-white/70 text-xs font-bold tracking-widest uppercase mb-1">{t.label}</p>
                <p className="text-white/25 text-xs leading-relaxed">{t.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

const ShirtSVG: React.FC<{ color: string; isDark: boolean }> = ({ color, isDark }) => (
  <svg viewBox="0 0 240 320" fill="none" className="w-full h-full">
    <path d="M100 30 L95 60 L120 75 L145 60 L140 30 Q120 45 100 30 Z" fill={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'} />
    <path d="M70 55 L30 80 L35 120 L75 100 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1.5" />
    <path d="M170 55 L210 80 L205 120 L165 100 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1.5" />
    <path d="M70 55 L75 100 L65 280 L175 280 L165 100 L170 55 L140 30 Q120 45 100 30 L70 55 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1.5" />
    <line x1="120" y1="75" x2="120" y2="278" stroke={isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.2)'} strokeWidth="1" />
    {[100, 125, 150, 175, 200, 225].map((y, i) => (
      <circle key={i} cx="120" cy={y} r="3" fill={isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)'} />
    ))}
    <rect x="82" y="105" width="28" height="24" rx="2" stroke={isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.2)'} strokeWidth="1.2" fill="none" />
    <line x1="82" y1="110" x2="110" y2="110" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="0.8" />
    <path d="M90 126 L96 114 L102 126 Z" stroke={isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)'} strokeWidth="1.2" fill="none" />
  </svg>
)

export default ShirtSection
