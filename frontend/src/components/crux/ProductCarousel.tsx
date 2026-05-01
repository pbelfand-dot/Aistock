import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Product, ColorVariant } from '../../data/products'

interface ProductCarouselProps {
  product: Product
}

// SVG product silhouettes keyed by product id
const ProductSilhouette: React.FC<{ productId: string; color: string; accentColor: string }> = ({
  productId,
  color,
  accentColor,
}) => {
  const isDark = accentColor === '#ffffff'

  if (productId === 'chalk-bag') {
    return (
      <svg viewBox="0 0 200 280" fill="none" className="w-full h-full drop-shadow-2xl">
        {/* Bag body */}
        <rect x="50" y="80" width="100" height="140" rx="12" fill={color} stroke={isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)'} strokeWidth="1.5" />
        {/* Drawstring top */}
        <path d="M60 80 Q100 60 140 80" stroke={isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)'} strokeWidth="3" fill="none" strokeLinecap="round" />
        <ellipse cx="100" cy="80" rx="40" ry="8" fill={isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'} />
        {/* Belt strap */}
        <rect x="130" y="88" width="8" height="55" rx="2" fill={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.18)'} />
        <rect x="134" y="88" width="14" height="4" rx="2" fill={isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)'} />
        {/* Carabiner */}
        <ellipse cx="142" cy="148" rx="10" ry="14" stroke={isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'} strokeWidth="2.5" fill="none" />
        <line x1="142" y1="134" x2="142" y2="142" stroke={isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'} strokeWidth="2.5" />
        {/* Mountain graphic on bag */}
        <path d="M80 190 L100 155 L120 190 Z" stroke={isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.3)'} strokeWidth="1.5" fill="none" />
        <path d="M85 190 L95 168 L100 174 L105 162 L115 190" stroke={isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.12)'} strokeWidth="0.8" fill="none" />
        {/* CRUXED label patch */}
        <rect x="74" y="198" width="52" height="14" rx="2" fill={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'} />
        <text x="100" y="208" textAnchor="middle" fontSize="6" fill={isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)'} fontFamily="monospace" letterSpacing="2">CRUXED</text>
      </svg>
    )
  }

  if (productId === 'ridge-pants') {
    return (
      <svg viewBox="0 0 220 340" fill="none" className="w-full h-full drop-shadow-2xl">
        {/* Waistband */}
        <rect x="50" y="50" width="120" height="20" rx="4" fill={isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.12)'} />
        <line x1="100" y1="50" x2="100" y2="55" stroke={isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)'} strokeWidth="2" />
        {/* Drawcord */}
        <path d="M90 52 Q100 48 110 52" stroke={isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'} strokeWidth="1.5" fill="none" />
        {/* Left leg */}
        <path d="M50 70 L70 70 L80 260 L55 270 L45 260 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" />
        {/* Right leg */}
        <path d="M150 70 L170 70 L175 260 L165 270 L140 260 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" />
        {/* Crotch */}
        <path d="M70 70 Q110 120 150 70" fill={color} stroke={isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'} strokeWidth="1" />
        {/* Panel seams */}
        <path d="M72 80 L78 200" stroke={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" strokeDasharray="4 3" />
        <path d="M152 80 L160 200" stroke={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" strokeDasharray="4 3" />
        {/* Articulated knee lines */}
        <path d="M55 175 Q62 170 70 175" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="1.5" fill="none" />
        <path d="M150 175 Q160 170 168 175" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="1.5" fill="none" />
        {/* Pocket zip left */}
        <line x1="56" y1="90" x2="68" y2="108" stroke={isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)'} strokeWidth="1.5" />
        <circle cx="56" cy="90" r="2" fill={isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.35)'} />
        {/* Cuff drawcord */}
        <path d="M48 260 Q55 265 62 260" stroke={isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)'} strokeWidth="1.5" fill="none" />
        <path d="M145 260 Q155 265 166 260" stroke={isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)'} strokeWidth="1.5" fill="none" />
        {/* Abstract matterhorn graphic on left thigh */}
        <path d="M58 130 L65 112 L72 130 Z" stroke={isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.18)'} strokeWidth="1" fill="none" />
        {/* CRUXED small text */}
        <text x="63" y="145" textAnchor="middle" fontSize="4" fill={isDark ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.2)'} fontFamily="monospace" letterSpacing="1">CRUXED</text>
      </svg>
    )
  }

  if (productId === 'ankle-sock') {
    return (
      <svg viewBox="0 0 220 200" fill="none" className="w-full h-full drop-shadow-2xl">
        {/* Sock body */}
        <path d="M60 30 L60 130 Q60 155 85 165 L140 165 Q165 165 165 140 L165 130 L145 130 L145 140 Q145 148 135 148 L90 148 Q80 148 80 140 L80 30 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'} strokeWidth="1.5" />
        {/* Cuff top */}
        <rect x="60" y="25" width="85" height="16" rx="4" fill={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} />
        {/* Knit texture lines */}
        {[45, 58, 71, 84, 97, 110].map((y, i) => (
          <line key={i} x1="63" y1={y} x2="142" y2={y} stroke={isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'} strokeWidth="0.8" strokeDasharray="3 2" />
        ))}
        {/* Arch compression band */}
        <rect x="63" y="105" width="79" height="10" rx="2" fill={isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)'} />
        {/* Mountain knit art */}
        <path d="M85 95 L100 72 L115 95 Z" stroke={isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)'} strokeWidth="1.2" fill="none" />
        <path d="M90 95 L100 78 L110 95" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="0.8" fill="none" />
        {/* Embroidered XX logo at top */}
        <text x="103" y="22" textAnchor="middle" fontSize="8" fill={isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)'} fontFamily="monospace" fontWeight="bold">✕✕</text>
        {/* Reinforced heel */}
        <path d="M80 132 Q80 148 90 148 L100 148 L100 130 Q88 130 80 132 Z" fill={isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'} />
        {/* Sole strip */}
        <path d="M80 148 Q80 155 90 158 L130 158 Q142 155 145 145 L100 145 Z" fill={isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'} />
        {/* MATTERHORN text on cuff */}
        <text x="102" y="37" textAnchor="middle" fontSize="4.5" fill={isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.28)'} fontFamily="monospace" letterSpacing="1.5">MATTERHORN</text>
      </svg>
    )
  }

  // Shirt fallback
  return (
    <svg viewBox="0 0 240 320" fill="none" className="w-full h-full drop-shadow-2xl">
      {/* Collar */}
      <path d="M100 30 L95 60 L120 75 L145 60 L140 30 Q120 45 100 30 Z" fill={isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'} />
      {/* Left sleeve */}
      <path d="M70 55 L30 80 L35 120 L75 100 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" />
      {/* Right sleeve */}
      <path d="M170 55 L210 80 L205 120 L165 100 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" />
      {/* Body */}
      <path d="M70 55 L75 100 L65 280 L175 280 L165 100 L170 55 L140 30 Q120 45 100 30 L70 55 Z" fill={color} stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'} strokeWidth="1" />
      {/* Button placket */}
      <line x1="120" y1="75" x2="120" y2="278" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="1" />
      {[100, 125, 150, 175, 200, 225].map((y, i) => (
        <circle key={i} cx="120" cy={y} r="2.5" fill={isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)'} />
      ))}
      {/* Chest pocket */}
      <rect x="82" y="105" width="28" height="24" rx="2" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="1" fill="none" />
      <line x1="82" y1="110" x2="110" y2="110" stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)'} strokeWidth="0.8" />
      {/* Mountain logo on pocket */}
      <path d="M90 126 L96 114 L102 126 Z" stroke={isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)'} strokeWidth="1.2" fill="none" />
    </svg>
  )
}

const ColorDot: React.FC<{ color: ColorVariant; active: boolean; onClick: () => void }> = ({
  color,
  active,
  onClick,
}) => (
  <button
    onClick={onClick}
    title={color.name}
    className={`relative rounded-full transition-all duration-300 ${
      active ? 'scale-110' : 'scale-100 hover:scale-105'
    }`}
    style={{ width: 28, height: 28 }}
  >
    <span
      className="absolute inset-0 rounded-full"
      style={{ backgroundColor: color.hex }}
    />
    {active && (
      <span className="absolute inset-0 rounded-full ring-2 ring-white ring-offset-2 ring-offset-black" />
    )}
  </button>
)

const ProductCarousel: React.FC<ProductCarouselProps> = ({ product }) => {
  const [activeColorIdx, setActiveColorIdx] = useState(0)
  const [sliding, setSliding] = useState(false)
  const [direction, setDirection] = useState<'left' | 'right'>('right')
  const [showSpecs, setShowSpecs] = useState(false)
  const slideRef = useRef<HTMLDivElement>(null)

  const activeColor = product.colors[activeColorIdx]

  const goTo = useCallback(
    (idx: number) => {
      if (idx === activeColorIdx || sliding) return
      setDirection(idx > activeColorIdx ? 'right' : 'left')
      setSliding(true)
      setTimeout(() => {
        setActiveColorIdx(idx)
        setSliding(false)
      }, 280)
    },
    [activeColorIdx, sliding]
  )

  const prev = () => goTo(activeColorIdx === 0 ? product.colors.length - 1 : activeColorIdx - 1)
  const next = () => goTo(activeColorIdx === product.colors.length - 1 ? 0 : activeColorIdx + 1)

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeColorIdx, sliding])

  const isDark = activeColor.accentHex === '#ffffff'
  const colorBg = activeColor.hex
  const slideAnim = sliding
    ? direction === 'right'
      ? 'translate-x-8 opacity-0'
      : '-translate-x-8 opacity-0'
    : 'translate-x-0 opacity-100'

  return (
    <section
      id={product.id}
      className="relative min-h-screen flex flex-col justify-center py-24 overflow-hidden transition-colors duration-700"
      style={{ backgroundColor: '#0a0a0a' }}
    >
      {/* Background color wash from product color */}
      <div
        className="absolute inset-0 opacity-15 transition-all duration-700"
        style={{ backgroundColor: colorBg }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-black/80 via-transparent to-black/80 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-6 w-full">
        {/* Section header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12">
          <div>
            <p className="text-white/30 text-xs tracking-[0.4em] uppercase mb-2">
              {String(product.colors.findIndex(c => c.id === activeColor.id) + 1).padStart(2, '0')} / {product.colors.length}
            </p>
            <h2 className="text-3xl md:text-5xl font-black text-white tracking-tight leading-none">
              {product.name}
            </h2>
            <p className="text-white/40 text-sm tracking-widest uppercase mt-2">{product.tagline}</p>
          </div>

          {/* Color selector */}
          <div className="mt-6 md:mt-0 flex items-center gap-4">
            <span className="text-white/40 text-xs tracking-widest uppercase">
              {activeColor.name}
            </span>
            <div className="flex items-center gap-2">
              {product.colors.map((c, i) => (
                <ColorDot key={c.id} color={c} active={i === activeColorIdx} onClick={() => goTo(i)} />
              ))}
            </div>
          </div>
        </div>

        {/* Main slide area */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Product visual */}
          <div className="relative flex items-center justify-center" style={{ minHeight: 400 }}>
            {/* Nav arrows */}
            <button
              onClick={prev}
              className="absolute left-0 z-10 w-10 h-10 flex items-center justify-center border border-white/10 text-white/40 hover:text-white hover:border-white/40 transition-all"
            >
              ←
            </button>
            <button
              onClick={next}
              className="absolute right-0 z-10 w-10 h-10 flex items-center justify-center border border-white/10 text-white/40 hover:text-white hover:border-white/40 transition-all"
            >
              →
            </button>

            {/* Color card */}
            <div
              ref={slideRef}
              className={`transition-all duration-280 ${slideAnim} flex items-center justify-center`}
              style={{ width: '100%', maxWidth: 380 }}
            >
              {/* Hexagonal/sharp container */}
              <div
                className="relative w-72 h-80 md:w-80 md:h-96 flex items-center justify-center"
                style={{
                  background: `radial-gradient(ellipse at 40% 30%, ${colorBg}dd, ${colorBg}88)`,
                  clipPath: 'polygon(8% 0%, 92% 0%, 100% 8%, 100% 92%, 92% 100%, 8% 100%, 0% 92%, 0% 8%)',
                }}
              >
                {/* Inner glow */}
                <div
                  className="absolute inset-4 opacity-20"
                  style={{
                    background: `radial-gradient(ellipse at center, ${colorBg}, transparent)`,
                    clipPath: 'polygon(8% 0%, 92% 0%, 100% 8%, 100% 92%, 92% 100%, 8% 100%, 0% 92%, 0% 8%)',
                  }}
                />

                {/* Color index badge */}
                <div className="absolute top-4 left-4 text-xs font-bold tracking-widest opacity-40" style={{ color: isDark ? '#fff' : '#000' }}>
                  {String(activeColorIdx + 1).padStart(2, '0')}
                </div>

                {/* Product silhouette */}
                <div className="w-48 h-56 md:w-56 md:h-64 relative z-10">
                  <ProductSilhouette productId={product.id} color={colorBg} accentColor={activeColor.accentHex} />
                </div>

                {/* Color name watermark */}
                <div
                  className="absolute bottom-4 right-4 text-[10px] tracking-[0.3em] uppercase font-bold opacity-30"
                  style={{ color: isDark ? '#fff' : '#000' }}
                >
                  {activeColor.name}
                </div>
              </div>
            </div>
          </div>

          {/* Product info */}
          <div className="flex flex-col gap-6">
            {/* Feature badges */}
            <div className="flex flex-wrap gap-2">
              {product.features.map(f => (
                <span
                  key={f.label}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-white/10 text-white/50 text-xs tracking-widest uppercase hover:border-white/30 hover:text-white/80 transition-all duration-200"
                >
                  <span className="text-white/30">{f.icon}</span>
                  {f.label}
                </span>
              ))}
            </div>

            {/* Specs */}
            {product.specs.length > 0 && (
              <div className="border-t border-white/5 pt-6">
                <p className="text-xs tracking-widest text-white/30 uppercase mb-3">Size & Fit</p>
                <div className="flex flex-col gap-1.5">
                  {product.specs.map(s => (
                    <div key={s.label} className="flex justify-between text-sm">
                      <span className="text-white/40">{s.label}</span>
                      <span className="text-white font-mono">{s.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Size chart for pants/socks */}
            {product.sizeChart && (
              <div className="border-t border-white/5 pt-6">
                <p className="text-xs tracking-widest text-white/30 uppercase mb-3">Size Chart (Men's)</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr>
                        {product.sizeChart.headers.map(h => (
                          <th key={h} className="text-left text-white/30 tracking-widest pb-2 pr-4">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {product.sizeChart.rows.map(row => (
                        <tr key={row.size} className="border-t border-white/5">
                          <td className="py-1.5 pr-4 text-white font-bold">{row.size}</td>
                          <td className="py-1.5 pr-4 text-white/60 font-mono">{row.col1}</td>
                          {row.col2 && <td className="py-1.5 pr-4 text-white/60 font-mono">{row.col2}</td>}
                          {row.col3 && <td className="py-1.5 pr-4 text-white/60 font-mono">{row.col3}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-white/25 text-xs mt-2 tracking-wide">{product.sizeChart.fitNote}</p>
              </div>
            )}

            {/* Materials */}
            <div className="border-t border-white/5 pt-6">
              <p className="text-xs tracking-widest text-white/30 uppercase mb-3">Materials</p>
              <div className="flex flex-col gap-1.5">
                {product.materials.map((m, i) => (
                  <p key={i} className="text-white/50 text-xs leading-relaxed">
                    <span className="text-white/20 mr-2">—</span>{m}
                  </p>
                ))}
              </div>
            </div>

            {/* CTA */}
            <div className="flex gap-3 pt-4">
              <button className="flex-1 py-3.5 bg-white text-black font-bold tracking-widest uppercase text-sm hover:bg-white/90 transition-all duration-200 hover:scale-[1.01]">
                Add to Cart
              </button>
              <button
                onClick={() => setShowSpecs(!showSpecs)}
                className="px-5 py-3.5 border border-white/20 text-white text-sm tracking-widest uppercase hover:border-white/50 transition-all duration-200"
              >
                Specs
              </button>
            </div>
          </div>
        </div>

        {/* Expandable tech breakdown */}
        <div className={`overflow-hidden transition-all duration-500 ${showSpecs ? 'max-h-[600px] mt-12' : 'max-h-0'}`}>
          <div className="border-t border-white/5 pt-10">
            <p className="text-xs tracking-[0.4em] text-white/30 uppercase mb-6">Technical Breakdown</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {product.techBreakdown.map(t => (
                <div key={t.label} className="flex flex-col gap-1">
                  <div className="w-6 h-px bg-white/20 mb-2" />
                  <p className="text-white/80 text-xs font-bold tracking-widest uppercase">{t.label}</p>
                  <p className="text-white/35 text-xs leading-relaxed">{t.description}</p>
                </div>
              ))}
            </div>

            {/* Construction */}
            <div className="mt-8 border-t border-white/5 pt-6">
              <p className="text-xs tracking-widest text-white/30 uppercase mb-3">Construction</p>
              <div className="flex flex-wrap gap-2">
                {product.construction.map(c => (
                  <span key={c} className="text-white/40 text-xs border border-white/8 px-3 py-1">
                    {c}
                  </span>
                ))}
              </div>
            </div>

            {/* Care */}
            <div className="mt-6 border-t border-white/5 pt-6">
              <p className="text-xs tracking-widest text-white/30 uppercase mb-3">Care Instructions</p>
              <div className="flex flex-wrap gap-3">
                {product.careIcons.map(c => (
                  <span key={c} className="text-white/30 text-xs">{c}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Slide progress dots */}
        <div className="flex justify-center gap-2 mt-10">
          {product.colors.map((_, i) => (
            <button
              key={i}
              onClick={() => goTo(i)}
              className={`transition-all duration-300 rounded-full ${
                i === activeColorIdx ? 'w-6 h-1.5 bg-white' : 'w-1.5 h-1.5 bg-white/20 hover:bg-white/40'
              }`}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

export default ProductCarousel
