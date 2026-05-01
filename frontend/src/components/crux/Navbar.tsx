import React, { useEffect, useState } from 'react'

const NAV_LINKS = [
  { label: 'Chalk Bag', href: '#chalk-bag' },
  { label: 'Ridge Pants', href: '#ridge-pants' },
  { label: 'Ankle Sock', href: '#ankle-sock' },
  { label: 'Shirt', href: '#matterhorn-shirt' },
]

const Navbar: React.FC = () => {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
        scrolled ? 'bg-black/90 backdrop-blur-md border-b border-white/5' : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <a href="#" className="flex items-center gap-3 group">
          <MountainLogoSmall />
          <div>
            <span className="text-white font-black text-lg tracking-tighter">CRUXED</span>
            <span className="block text-white/30 text-[9px] tracking-[0.3em] uppercase leading-none">
              Climb. Conquer. Evolve.
            </span>
          </div>
        </a>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map(link => (
            <a
              key={link.href}
              href={link.href}
              className="text-white/50 hover:text-white text-xs tracking-widest uppercase transition-colors duration-200"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-4">
          <a
            href="#products"
            className="px-5 py-2 border border-white/20 text-white text-xs tracking-widest uppercase hover:bg-white hover:text-black transition-all duration-300"
          >
            Shop All
          </a>
        </div>

        {/* Mobile toggle */}
        <button
          className="md:hidden flex flex-col gap-1.5 p-2"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <span className={`block w-6 h-px bg-white transition-all duration-300 ${menuOpen ? 'rotate-45 translate-y-2' : ''}`} />
          <span className={`block w-6 h-px bg-white transition-all duration-300 ${menuOpen ? 'opacity-0' : ''}`} />
          <span className={`block w-6 h-px bg-white transition-all duration-300 ${menuOpen ? '-rotate-45 -translate-y-2' : ''}`} />
        </button>
      </div>

      {/* Mobile menu */}
      <div className={`md:hidden overflow-hidden transition-all duration-300 ${menuOpen ? 'max-h-64' : 'max-h-0'}`}>
        <div className="bg-black/95 backdrop-blur-md border-t border-white/5 px-6 py-4 flex flex-col gap-4">
          {NAV_LINKS.map(link => (
            <a
              key={link.href}
              href={link.href}
              className="text-white/60 hover:text-white text-sm tracking-widest uppercase"
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
    </nav>
  )
}

const MountainLogoSmall: React.FC = () => (
  <svg width="28" height="24" viewBox="0 0 60 48" fill="none">
    <path d="M30 2L2 46h56L30 2z" stroke="white" strokeWidth="2" fill="none" />
    <path d="M30 2L18 28L30 22L42 28L30 2z" fill="white" opacity="0.2" />
  </svg>
)

export default Navbar
