import React, { useEffect, useRef } from 'react'

const pillars = [
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    title: 'Portuguese Heritage',
    body: 'Our linens are woven on century-old looms in Guimarães — the cradle of Portuguese textile craft. Each thread carries four generations of knowledge.',
  },
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" strokeLinecap="round" />
      </svg>
    ),
    title: 'Unhurried Process',
    body: 'We refuse to rush. Pattern, cut, and finish are each considered in isolation — then as a whole. Good clothing takes time. Ours takes the time it deserves.',
  },
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    title: 'Considered Restraint',
    body: 'No logos. No loud colours. No seasonal fads. We design for the wardrobe that outlasts trends and grows more distinguished with each passing summer.',
  },
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
    title: 'Long Island Provenance',
    body: 'Conceived at the intersection of ocean and estate — where old money meets the Atlantic. That tension between ease and elegance defines every piece.',
  },
]

const Craftsmanship: React.FC = () => {
  const refs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)]

  useEffect(() => {
    refs.forEach(ref => {
      const el = ref.current
      if (!el) return
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
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
    <section id="craftsmanship" className="py-28 bg-ivory">
      <div className="max-w-7xl mx-auto px-6 lg:px-12">

        {/* Header */}
        <div ref={refs[0]} className="animate-on-scroll text-center mb-24">
          <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold block mb-4">
            — The Atelier —
          </span>
          <h2 className="font-serif font-light text-5xl lg:text-6xl text-navy mb-6">
            Craft without<br />
            <em>compromise</em>
          </h2>
          <p className="font-sans text-sm text-muted font-light max-w-md mx-auto leading-relaxed">
            We believe the finest things are made slowly, by hands that care,
            from materials that respect both nature and wearer.
          </p>
        </div>

        {/* Full-width feature panel */}
        <div ref={refs[1]} className="animate-on-scroll relative mb-24 overflow-hidden" style={{ transitionDelay: '0.1s' }}>
          <div className="bg-gradient-to-r from-navy-dark to-navy h-64 lg:h-80 flex items-center justify-center relative">
            <div className="absolute inset-0 opacity-5"
              style={{
                backgroundImage: `repeating-linear-gradient(-45deg, #C9A84C 0, #C9A84C 1px, transparent 0, transparent 50%)`,
                backgroundSize: '16px 16px',
              }}
            />
            <blockquote className="text-center px-8 relative z-10">
              <p className="font-serif italic text-2xl lg:text-4xl text-ivory/90 max-w-2xl mx-auto leading-relaxed mb-6">
                "Elegance is not about being noticed,<br />it is about being remembered."
              </p>
              <div className="h-px w-16 bg-gold/50 mx-auto mb-4" />
              <cite className="font-sans text-[0.65rem] tracking-widest uppercase text-gold/70 not-italic">
                L.I. Beachwear · Atelier Philosophy
              </cite>
            </blockquote>
          </div>
        </div>

        {/* Pillars grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10">
          {pillars.map((pillar, i) => (
            <div
              key={pillar.title}
              ref={refs[i + 2] as React.RefObject<HTMLDivElement>}
              className="animate-on-scroll group"
              style={{ transitionDelay: `${i * 0.1}s` }}
            >
              <div className="text-gold mb-6 group-hover:text-gold-light transition-colors duration-300">
                {pillar.icon}
              </div>
              <div className="h-px w-8 bg-gold/40 mb-5 group-hover:w-14 transition-all duration-500" />
              <h3 className="font-serif text-xl text-navy mb-4">{pillar.title}</h3>
              <p className="font-sans text-sm text-muted font-light leading-relaxed">{pillar.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default Craftsmanship
