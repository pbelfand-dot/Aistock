import React, { useEffect, useRef } from 'react'

interface Collection {
  name: string
  subtitle: string
  description: string
  tag: string
  color: string
  gradient: string
  accentColor: string
}

const collections: Collection[] = [
  {
    name: 'The Newport',
    subtitle: 'Summer Collection',
    description: 'Refined linen and silk blends in muted coastal palettes. Each piece a quiet statement.',
    tag: 'Signature',
    color: '#E8DFD0',
    gradient: 'from-[#2C3E2D] via-[#3D5C3E] to-[#2C4A3A]',
    accentColor: '#C9A84C',
  },
  {
    name: 'The Montauk',
    subtitle: 'Resort Essentials',
    description: 'Sun-bleached cotton and Portuguese terry. Built for salt air and unhurried mornings.',
    tag: 'New Arrival',
    color: '#D4C5A9',
    gradient: 'from-[#1B2A4A] via-[#2C3E60] to-[#1B3A5A]',
    accentColor: '#D4B86A',
  },
  {
    name: 'The Gatsby',
    subtitle: 'Evening Coastal',
    description: 'Where the day transitions to dusk — draped in champagne-weight silk and satin trim.',
    tag: 'Exclusive',
    color: '#F5F0E8',
    gradient: 'from-[#3D3020] via-[#5A4530] to-[#3D2A15]',
    accentColor: '#E8D9A8',
  },
]

const CollectionCard: React.FC<{ item: Collection; index: number }> = ({ item, index }) => {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible')
          observer.disconnect()
        }
      },
      { threshold: 0.15 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className="animate-on-scroll collection-card group relative overflow-hidden"
      style={{ transitionDelay: `${index * 0.12}s` }}
    >
      {/* Background gradient as "image" */}
      <div className={`relative h-[480px] lg:h-[580px] bg-gradient-to-br ${item.gradient} overflow-hidden`}>
        {/* Decorative pattern */}
        <div
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage: `repeating-linear-gradient(45deg, ${item.accentColor} 0, ${item.accentColor} 1px, transparent 0, transparent 50%)`,
            backgroundSize: '20px 20px',
          }}
        />
        {/* Glow */}
        <div
          className="absolute bottom-0 left-0 right-0 h-1/2 opacity-20"
          style={{ background: `radial-gradient(ellipse at 50% 100%, ${item.accentColor} 0%, transparent 70%)` }}
        />
        {/* Ornamental lines */}
        <div className="absolute top-10 left-10 w-16 h-px bg-gradient-to-r from-transparent to-current opacity-30" style={{ color: item.accentColor }} />
        <div className="absolute top-10 left-10 w-px h-16 bg-gradient-to-b from-transparent to-current opacity-30" style={{ color: item.accentColor }} />
        <div className="absolute bottom-32 right-10 w-16 h-px bg-gradient-to-l from-transparent to-current opacity-30" style={{ color: item.accentColor }} />
        <div className="absolute bottom-16 right-10 w-px h-16 bg-gradient-to-t from-transparent to-current opacity-30" style={{ color: item.accentColor }} />

        {/* Tag */}
        <div className="absolute top-8 right-8">
          <span
            className="font-sans text-[0.6rem] tracking-widest uppercase py-1.5 px-3 border"
            style={{ color: item.accentColor, borderColor: `${item.accentColor}50` }}
          >
            {item.tag}
          </span>
        </div>

        {/* Content overlay */}
        <div className="absolute bottom-0 left-0 right-0 p-8">
          <p
            className="font-sans text-[0.6rem] tracking-widest3 uppercase mb-3"
            style={{ color: `${item.accentColor}99` }}
          >
            {item.subtitle}
          </p>
          <h3
            className="font-serif font-light text-4xl mb-4 leading-tight"
            style={{ color: item.color }}
          >
            {item.name}
          </h3>
          <p
            className="font-sans text-sm font-light leading-relaxed mb-6 opacity-0 group-hover:opacity-100 transition-opacity duration-500 max-w-xs"
            style={{ color: `${item.color}99` }}
          >
            {item.description}
          </p>
          <a
            href="#collections"
            className="inline-flex items-center gap-3 font-sans text-xs tracking-widest uppercase transition-all duration-300 opacity-0 group-hover:opacity-100"
            style={{ color: item.accentColor }}
          >
            <span>View Collection</span>
            <span className="block w-6 h-px" style={{ background: item.accentColor }} />
          </a>
        </div>
      </div>
    </div>
  )
}

const Collections: React.FC = () => {
  const headerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = headerRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible')
          observer.disconnect()
        }
      },
      { threshold: 0.2 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <section id="collections" className="py-28 px-6 lg:px-12 bg-ivory">
      <div className="max-w-7xl mx-auto">
        {/* Section header */}
        <div ref={headerRef} className="animate-on-scroll text-center mb-20">
          <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold mb-4 block">
            — Curated for the Discerning —
          </span>
          <h2 className="font-serif font-light text-5xl lg:text-6xl text-navy mb-6">
            Our Collections
          </h2>
          <p className="font-sans text-sm text-muted font-light tracking-wide max-w-lg mx-auto leading-relaxed">
            Each collection is conceived as a chapter — a narrative woven in fabric,
            colour, and craft that speaks without raising its voice.
          </p>
        </div>

        {/* Cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {collections.map((item, i) => (
            <CollectionCard key={item.name} item={item} index={i} />
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="text-center mt-16">
          <a href="#shop" className="btn-outline">
            View All Collections
          </a>
        </div>
      </div>
    </section>
  )
}

export default Collections
