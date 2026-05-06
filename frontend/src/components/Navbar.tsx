import React, { useState, useEffect } from 'react'

const Navbar: React.FC = () => {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const navLinks = ['Collections', 'Our Story', 'Craftsmanship', 'Contact']

  return (
    <>
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 navbar-blur ${
          scrolled
            ? 'bg-ivory/90 border-b border-gold/20 py-3'
            : 'bg-transparent py-6'
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 lg:px-12 flex items-center justify-between">
          {/* Left nav links */}
          <div className="hidden lg:flex items-center gap-10">
            {navLinks.slice(0, 2).map(link => (
              <a
                key={link}
                href={`#${link.toLowerCase().replace(' ', '-')}`}
                className={`hover-gold-underline font-sans text-xs tracking-widest uppercase transition-colors duration-300 ${
                  scrolled ? 'text-charcoal' : 'text-ivory/90'
                } hover:text-gold`}
              >
                {link}
              </a>
            ))}
          </div>

          {/* Logo — center */}
          <a href="#" className="flex flex-col items-center group">
            <span
              className={`font-display text-2xl tracking-widest3 transition-colors duration-300 ${
                scrolled ? 'text-navy' : 'text-ivory'
              }`}
            >
              L.I.
            </span>
            <span
              className={`font-sans text-[0.55rem] tracking-widest2 uppercase mt-0.5 transition-colors duration-300 ${
                scrolled ? 'text-tan' : 'text-ivory/70'
              }`}
            >
              Beachwear
            </span>
          </a>

          {/* Right nav links */}
          <div className="hidden lg:flex items-center gap-10">
            {navLinks.slice(2).map(link => (
              <a
                key={link}
                href={`#${link.toLowerCase().replace(' ', '-')}`}
                className={`hover-gold-underline font-sans text-xs tracking-widest uppercase transition-colors duration-300 ${
                  scrolled ? 'text-charcoal' : 'text-ivory/90'
                } hover:text-gold`}
              >
                {link}
              </a>
            ))}
            <button
              className={`font-sans text-xs tracking-widest uppercase transition-colors duration-300 ${
                scrolled ? 'text-charcoal' : 'text-ivory/90'
              } hover:text-gold`}
              aria-label="Shopping bag"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
              </svg>
            </button>
          </div>

          {/* Mobile menu button */}
          <button
            className={`lg:hidden transition-colors duration-300 ${scrolled ? 'text-charcoal' : 'text-ivory'}`}
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Menu"
          >
            {menuOpen ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {/* Mobile menu */}
      <div
        className={`fixed inset-0 z-40 bg-navy/95 navbar-blur flex flex-col items-center justify-center transition-all duration-500 lg:hidden ${
          menuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
      >
        <div className="flex flex-col items-center gap-10">
          {navLinks.map((link, i) => (
            <a
              key={link}
              href={`#${link.toLowerCase().replace(' ', '-')}`}
              onClick={() => setMenuOpen(false)}
              className="font-serif text-3xl text-ivory/90 hover:text-gold transition-colors duration-300"
              style={{ transitionDelay: `${i * 60}ms` }}
            >
              {link}
            </a>
          ))}
          <a href="#shop" onClick={() => setMenuOpen(false)} className="btn-ghost mt-4">
            Shop Now
          </a>
        </div>
      </div>
    </>
  )
}

export default Navbar
