import React, { useEffect, useRef } from 'react'

const pieces = [
  {
    name: 'The Lido Shirt',
    material: 'Sea Island Cotton',
    price: '£285',
    color: 'Ecru / Champagne',
    gradient: 'from-[#C9A84C]/20 to-[#8B7355]/30',
    bg: '#EDE8DC',
  },
  {
    name: 'The Harbour Trunk',
    material: 'Portuguese Linen',
    price: '£195',
    color: 'Navy / Natural',
    gradient: 'from-[#1B2A4A]/80 to-[#2C3E60]/90',
    bg: '#1B2A4A',
  },
  {
    name: 'The Shore Wrap',
    material: 'Silk Jacquard',
    price: '£340',
    color: 'Ivory / Gold',
    gradient: 'from-[#2C3E2D]/70 to-[#3D5C3E]/80',
    bg: '#2C3E2D',
  },
  {
    name: 'The Cove Tote',
    material: 'Full-Grain Leather',
    price: '£420',
    color: 'Natural Tan',
    gradient: 'from-[#8B7355]/60 to-[#6E5B40]/80',
    bg: '#8B7355',
  },
]

const Featured: React.FC = () => {
  const headerRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    [headerRef, gridRef].forEach(ref => {
      const el = ref.current
      if (!el) return
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            el.querySelectorAll('.animate-on-scroll').forEach((child, i) => {
              setTimeout(() => child.classList.add('visible'), i * 100)
            })
            el.classList.add('visible')
            observer.disconnect()
          }
        },
        { threshold: 0.1 }
      )
      observer.observe(el)
      return () => observer.disconnect()
    })
  }, [])

  return (
    <section id="shop" className="py-28 bg-parchment">
      <div className="max-w-7xl mx-auto px-6 lg:px-12">
        {/* Header */}
        <div ref={headerRef} className="animate-on-scroll flex flex-col md:flex-row md:items-end justify-between mb-16">
          <div>
            <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold block mb-4">
              — Signature Pieces —
            </span>
            <h2 className="font-serif font-light text-5xl text-navy">
              Selected Works
            </h2>
          </div>
          <a href="#collections" className="btn-outline mt-8 md:mt-0 self-start md:self-auto">
            Full Catalogue
          </a>
        </div>

        {/* Product grid */}
        <div ref={gridRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {pieces.map((piece, i) => (
            <div
              key={piece.name}
              className="animate-on-scroll collection-card group cursor-pointer"
              style={{ transitionDelay: `${i * 0.1}s` }}
            >
              {/* Product visual */}
              <div
                className={`relative h-64 bg-gradient-to-br ${piece.gradient} overflow-hidden mb-5`}
                style={{ backgroundColor: piece.bg }}
              >
                {/* Subtle fabric texture */}
                <div
                  className="absolute inset-0 opacity-[0.07]"
                  style={{
                    backgroundImage: `repeating-linear-gradient(0deg, #C9A84C 0, #C9A84C 1px, transparent 0, transparent 4px),
                      repeating-linear-gradient(90deg, #C9A84C 0, #C9A84C 1px, transparent 0, transparent 4px)`,
                  }}
                />
                {/* Centered monogram */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="font-display text-6xl opacity-10 text-ivory">{piece.name.split(' ')[1][0]}</div>
                </div>
                {/* Quick add overlay */}
                <div className="absolute inset-0 bg-navy/0 group-hover:bg-navy/30 transition-all duration-400 flex items-end justify-center pb-6 opacity-0 group-hover:opacity-100">
                  <button className="btn-ghost text-xs px-5 py-2.5">
                    Quick View
                  </button>
                </div>
              </div>

              {/* Product info */}
              <div>
                <p className="font-sans text-[0.6rem] tracking-widest uppercase text-muted/70 mb-1">
                  {piece.material}
                </p>
                <h3 className="font-serif text-xl text-charcoal mb-1 group-hover:text-navy transition-colors duration-300">
                  {piece.name}
                </h3>
                <p className="font-sans text-xs text-muted mb-3">{piece.color}</p>
                <div className="flex items-center justify-between">
                  <span className="font-serif text-lg text-navy">{piece.price}</span>
                  <button className="font-sans text-[0.6rem] tracking-widest uppercase text-gold hover:text-gold-dark transition-colors duration-300">
                    Add to Bag
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default Featured
