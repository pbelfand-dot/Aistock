import React, { useEffect, useRef } from 'react'

const pieces = [
  {
    name: 'Jones Beach Tee',
    material: 'Heavyweight Cotton',
    price: '$40',
    color: 'Natural / Navy',
    description: 'Oversized fit. Jones Beach sketch on back, L.I Beachwear chest hit. Garment-washed for a lived-in feel.',
    tag: 'Drop 01',
    bg: '#EDE8DC',
    gradient: 'from-[#EDE8DC] to-[#D4C5A9]',
    textColor: '#1B2A4A',
    accentColor: '#1B2A4A',
    stripeColor: null,
  },
  {
    name: 'Jones Beach Swim Short',
    material: 'Custom Toile Print',
    price: '$50',
    color: 'Powder Blue / Ivory',
    description: 'Custom Jones Beach print. Elastic waistband with rope drawstring. Back pocket with drainage. Woven L.I label.',
    tag: 'Signature',
    bg: '#B8CDD9',
    gradient: 'from-[#B8CDD9] to-[#8AAFC0]',
    textColor: '#1B2A4A',
    accentColor: '#F5F0E8',
    stripeColor: '#F5F0E8',
  },
  {
    name: 'Linen Beach Pant',
    material: 'Portuguese Linen',
    price: '$80',
    color: 'Ivory · Navy · Oatmeal · Charcoal',
    description: 'Wide-leg linen in four colourways. Elastic waist, relaxed drape. Made for salt air and slow mornings.',
    tag: 'Essentials',
    bg: '#2A2A2A',
    gradient: 'from-[#2A2A2A] to-[#1B2A4A]',
    textColor: '#F5F0E8',
    accentColor: '#C9A84C',
    stripeColor: null,
  },
  {
    name: 'Jones Beach Sandal',
    material: 'Full-Grain Leather',
    price: '$130',
    color: 'Espresso Brown',
    description: 'Leather strap. Engraved Jones Beach footbed. Triple-layer EVA sole with wave-pattern grip. Built to last seasons.',
    tag: 'Limited',
    bg: '#3D2B1A',
    gradient: 'from-[#3D2B1A] to-[#5C3D20]',
    textColor: '#E8C99A',
    accentColor: '#C9A84C',
    stripeColor: null,
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
                className={`relative h-72 bg-gradient-to-br ${piece.gradient} overflow-hidden mb-5`}
                style={{ backgroundColor: piece.bg }}
              >
                {/* Stripe overlay for swim short */}
                {piece.stripeColor && (
                  <div
                    className="absolute inset-0 opacity-40"
                    style={{
                      backgroundImage: `repeating-linear-gradient(90deg, ${piece.stripeColor} 0, ${piece.stripeColor} 28px, transparent 28px, transparent 56px)`,
                    }}
                  />
                )}
                {/* Fabric weave texture */}
                <div
                  className="absolute inset-0 opacity-[0.04]"
                  style={{
                    backgroundImage: `repeating-linear-gradient(0deg, #fff 0, #fff 1px, transparent 0, transparent 3px),
                      repeating-linear-gradient(90deg, #fff 0, #fff 1px, transparent 0, transparent 3px)`,
                  }}
                />
                {/* Tag badge */}
                <div className="absolute top-5 left-5">
                  <span
                    className="font-sans text-[0.55rem] tracking-widest uppercase py-1 px-2.5 border"
                    style={{ color: piece.accentColor, borderColor: `${piece.accentColor}50` }}
                  >
                    {piece.tag}
                  </span>
                </div>
                {/* Centered product initial */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="font-display text-8xl opacity-[0.07]" style={{ color: piece.textColor }}>
                    {piece.name.split(' ')[0][0]}
                  </span>
                </div>
                {/* Hover overlay */}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-all duration-500 flex items-end justify-center pb-6 opacity-0 group-hover:opacity-100">
                  <button className="font-sans text-[0.65rem] tracking-widest uppercase py-2.5 px-5 border border-white/60 text-white hover:bg-white/10 transition-colors duration-300">
                    Quick View
                  </button>
                </div>
                {/* Description on hover */}
                <div className="absolute bottom-0 left-0 right-0 p-5 translate-y-full group-hover:translate-y-0 transition-transform duration-500 bg-gradient-to-t from-black/70 to-transparent">
                  <p className="font-sans text-[0.65rem] text-white/80 leading-relaxed">{piece.description}</p>
                </div>
              </div>

              {/* Product info */}
              <div>
                <p className="font-sans text-[0.6rem] tracking-widest uppercase text-muted/70 mb-1.5">
                  {piece.material}
                </p>
                <h3 className="font-serif text-xl text-charcoal mb-1 group-hover:text-navy transition-colors duration-300">
                  {piece.name}
                </h3>
                <p className="font-sans text-xs text-muted mb-4 leading-relaxed">{piece.color}</p>
                <div className="flex items-center justify-between">
                  <span className="font-serif text-xl text-navy">{piece.price}</span>
                  <button className="font-sans text-[0.6rem] tracking-widest uppercase text-gold hover:text-gold-dark transition-colors duration-300 border-b border-gold/0 hover:border-gold/50 pb-0.5">
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
