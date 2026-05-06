import React, { useEffect, useRef, useState } from 'react'

const Newsletter: React.FC = () => {
  const ref = useRef<HTMLDivElement>(null)
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

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
      { threshold: 0.2 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (email) setSubmitted(true)
  }

  return (
    <section className="py-28 bg-navy relative overflow-hidden">
      {/* Background decoration */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: `repeating-linear-gradient(45deg, #C9A84C 0, #C9A84C 1px, transparent 0, transparent 40px)`,
        }}
      />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-px h-16 bg-gradient-to-b from-transparent to-gold/30" />

      <div ref={ref} className="animate-on-scroll relative z-10 max-w-2xl mx-auto px-6 text-center">
        <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold/70 block mb-6">
          — Join the Circle —
        </span>
        <h2 className="font-serif font-light text-4xl lg:text-5xl text-ivory mb-6 leading-tight">
          First to know.<br />
          <em className="text-gold/80">Always.</em>
        </h2>
        <p className="font-sans font-light text-sm text-ivory/50 tracking-wide mb-12 max-w-sm mx-auto leading-relaxed">
          Private collection previews, limited releases, and the occasional note
          from the atelier — never more than necessary.
        </p>

        {submitted ? (
          <div className="py-6">
            <div className="h-px w-16 bg-gold/40 mx-auto mb-6" />
            <p className="font-serif italic text-2xl text-ivory/80">You are on the list.</p>
            <p className="font-sans text-xs tracking-widest uppercase text-gold/60 mt-3">
              Welcome to the circle
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto">
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="Your email address"
              required
              className="flex-1 bg-transparent border border-ivory/20 text-ivory placeholder-ivory/30 font-sans text-xs tracking-wide px-5 py-3.5 focus:outline-none focus:border-gold/50 transition-colors duration-300"
            />
            <button type="submit" className="btn-ghost shrink-0 py-3.5">
              Subscribe
            </button>
          </form>
        )}

        <p className="font-sans text-[0.6rem] tracking-wide text-ivory/25 mt-6">
          Your privacy is respected. Unsubscribe at any time.
        </p>
      </div>
    </section>
  )
}

export default Newsletter
