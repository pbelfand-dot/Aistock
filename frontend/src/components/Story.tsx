import React, { useEffect, useRef } from 'react'

const useScrollReveal = (ref: React.RefObject<HTMLElement>) => {
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
}

const Story: React.FC = () => {
  const leftRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const statsRef = useRef<HTMLDivElement>(null)

  useScrollReveal(leftRef as React.RefObject<HTMLElement>)
  useScrollReveal(rightRef as React.RefObject<HTMLElement>)
  useScrollReveal(statsRef as React.RefObject<HTMLElement>)

  return (
    <section id="our-story" className="py-28 bg-cream">
      <div className="max-w-7xl mx-auto px-6 lg:px-12">

        {/* Main story grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center mb-24">
          {/* Left — decorative panel */}
          <div ref={leftRef} className="animate-on-scroll relative">
            {/* Framed art panel */}
            <div className="relative">
              <div className="absolute -top-4 -left-4 w-full h-full border border-gold/20" />
              <div className="bg-gradient-to-br from-navy via-navy-light to-forest h-[500px] relative overflow-hidden">
                {/* Interior decoration */}
                <div className="absolute inset-8 border border-ivory/10" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="font-display text-7xl text-ivory/10 mb-4 leading-none">L.I.</div>
                    <div className="h-px w-32 bg-gold/30 mx-auto mb-6" />
                    <div className="font-serif italic text-2xl text-ivory/40">Since 2024</div>
                    <div className="h-px w-32 bg-gold/30 mx-auto mt-6" />
                  </div>
                </div>
                {/* Corner ornaments */}
                {['top-6 left-6', 'top-6 right-6', 'bottom-6 left-6', 'bottom-6 right-6'].map((pos, i) => (
                  <div key={i} className={`absolute ${pos} w-5 h-5`}>
                    <div className="absolute top-0 left-0 w-full h-px bg-gold/40" />
                    <div className="absolute top-0 left-0 w-px h-full bg-gold/40" />
                  </div>
                ))}
                <div className="absolute top-6 right-6 w-5 h-5">
                  <div className="absolute top-0 right-0 w-full h-px bg-gold/40" />
                  <div className="absolute top-0 right-0 w-px h-full bg-gold/40" />
                </div>
                <div className="absolute bottom-6 right-6 w-5 h-5">
                  <div className="absolute bottom-0 right-0 w-full h-px bg-gold/40" />
                  <div className="absolute bottom-0 right-0 w-px h-full bg-gold/40" />
                </div>
                <div className="absolute bottom-6 left-6 w-5 h-5">
                  <div className="absolute bottom-0 left-0 w-full h-px bg-gold/40" />
                  <div className="absolute bottom-0 left-0 w-px h-full bg-gold/40" />
                </div>
              </div>
              <div className="absolute -bottom-4 -right-4 w-full h-full border border-gold/10" />
            </div>
          </div>

          {/* Right — text */}
          <div ref={rightRef} className="animate-on-scroll" style={{ transitionDelay: '0.2s' }}>
            <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold block mb-6">
              — Our Heritage —
            </span>
            <h2 className="font-serif font-light text-5xl text-navy mb-8 leading-tight">
              Born from the<br />
              <em>shores of Long Island</em>
            </h2>
            <div className="h-px w-12 bg-gold mb-8" />
            <p className="font-sans font-light text-sm text-muted leading-relaxed mb-6">
              L.I. Beachwear was conceived on the belief that true luxury is felt, not flaunted.
              Rooted in the understated elegance of Long Island's North Shore, our pieces carry
              the quiet confidence of those who have always known their worth.
            </p>
            <p className="font-sans font-light text-sm text-muted leading-relaxed mb-10">
              Every garment is a distillation of heritage craft and contemporary restraint —
              fabrics sourced from the finest Portuguese mills, hand-finished by artisans
              who understand that the details matter most when nobody is looking.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <a href="#craftsmanship" className="btn-primary">
                Our Craft
              </a>
              <a href="#contact" className="btn-outline">
                Enquire
              </a>
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div ref={statsRef} className="animate-on-scroll grid grid-cols-2 md:grid-cols-4 gap-px bg-gold/20">
          {[
            { value: '100%', label: 'Natural Fibres' },
            { value: '12', label: 'Artisan Partners' },
            { value: '3', label: 'Annual Collections' },
            { value: '∞', label: 'Season Wearability' },
          ].map((stat, i) => (
            <div
              key={stat.label}
              className="bg-cream p-10 text-center"
              style={{ transitionDelay: `${i * 0.1}s` }}
            >
              <div className="font-serif text-4xl text-navy mb-2">{stat.value}</div>
              <div className="font-sans text-[0.6rem] tracking-widest uppercase text-muted">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default Story
