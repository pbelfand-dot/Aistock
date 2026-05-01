import React, { useEffect, useRef } from 'react'

const STATS = [
  { value: '5', unit: 'Colorways', label: 'Per Product' },
  { value: '4', unit: 'Products', label: 'Matterhorn Drop' },
  { value: '100%', unit: 'Nylon', label: 'Ripstop Outer' },
  { value: 'YKK®', unit: 'Zippers', label: 'Throughout' },
]

const BrandSection: React.FC = () => {
  const sectionRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in-view')
          }
        })
      },
      { threshold: 0.1 }
    )
    const els = sectionRef.current?.querySelectorAll('.reveal')
    els?.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  return (
    <section ref={sectionRef} id="products" className="relative bg-black py-32 overflow-hidden">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: 'linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      {/* Mountain silhouette background */}
      <div className="absolute bottom-0 left-0 right-0 flex justify-center opacity-5 pointer-events-none">
        <svg viewBox="0 0 1200 300" className="w-full" fill="white">
          <path d="M0 300 L200 300 L400 80 L500 160 L600 20 L700 140 L800 60 L1000 300 L0 300 Z" />
        </svg>
      </div>

      <div className="max-w-7xl mx-auto px-6 relative">
        {/* Brand statement */}
        <div className="text-center mb-20">
          <p className="text-white/20 text-xs tracking-[0.5em] uppercase mb-4 reveal slide-up">
            The Matterhorn Collection
          </p>
          <h2
            className="text-4xl md:text-7xl font-black text-white tracking-tight leading-none mb-8 reveal slide-up"
            style={{ animationDelay: '0.1s' }}
          >
            CRUXED IS MORE
            <br />
            <span className="text-white/20">THAN GEAR.</span>
          </h2>
          <p
            className="text-xl md:text-2xl text-white/40 tracking-[0.2em] uppercase reveal slide-up"
            style={{ animationDelay: '0.2s' }}
          >
            IT'S A MINDSET.
          </p>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/5 mb-20 reveal slide-up" style={{ animationDelay: '0.3s' }}>
          {STATS.map(stat => (
            <div key={stat.label} className="bg-black p-8 text-center">
              <div className="text-4xl font-black text-white mb-1">{stat.value}</div>
              <div className="text-white/50 text-xs tracking-widest uppercase">{stat.unit}</div>
              <div className="text-white/20 text-xs tracking-wider mt-1">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Brand pillars */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/5">
          {[
            {
              num: '01',
              title: 'BUILT FOR CLIMBERS',
              body:
                'Every product in the Matterhorn collection is engineered for the demands of bouldering — chalk dust, high steps, harness wear, and long sessions at the wall.',
            },
            {
              num: '02',
              title: 'INSPIRED BY THE PEAK',
              body:
                'The Matterhorn is the world\'s most iconic peak. Its silhouette is etched into every garment — a reminder of what\'s possible when you push beyond the crux.',
            },
            {
              num: '03',
              title: 'FOR THE OBSESSED',
              body:
                'Not for the casual weekend warrior. Built for those who return to the same problem until it breaks. For the driven. For those who climb.',
            },
          ].map((p, i) => (
            <div
              key={p.num}
              className={`bg-black p-8 reveal slide-up`}
              style={{ animationDelay: `${0.1 * i}s` }}
            >
              <div className="text-white/15 text-xs font-mono mb-4">{p.num}</div>
              <h3 className="text-white font-bold tracking-widest text-sm uppercase mb-4">{p.title}</h3>
              <p className="text-white/35 text-sm leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default BrandSection
