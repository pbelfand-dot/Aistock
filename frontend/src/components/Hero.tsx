import React, { useEffect, useRef } from 'react'

const Hero: React.FC = () => {
  const videoRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    const onMove = (e: MouseEvent) => {
      const { left, top, width, height } = el.getBoundingClientRect()
      const x = ((e.clientX - left) / width - 0.5) * 12
      const y = ((e.clientY - top) / height - 0.5) * 8
      el.style.transform = `translate(${x}px, ${y}px)`
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-navy-dark">
      {/* Background gradient mosaic */}
      <div className="absolute inset-0">
        {/* Deep ocean gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-navy-dark via-navy to-forest-dark opacity-95" />
        {/* Subtle texture overlay */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23C9A84C' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
          }}
        />
        {/* Gold vignette corners */}
        <div className="absolute top-0 left-0 w-64 h-64 bg-gold/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-gold/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-forest/20 rounded-full blur-3xl" />
      </div>

      {/* Floating abstract shapes */}
      <div ref={videoRef} className="absolute inset-0 pointer-events-none transition-transform duration-700 ease-out">
        <div className="absolute top-1/4 left-1/6 w-px h-40 bg-gradient-to-b from-transparent via-gold/30 to-transparent" />
        <div className="absolute top-1/3 right-1/5 w-px h-32 bg-gradient-to-b from-transparent via-gold/20 to-transparent" />
        <div className="absolute bottom-1/3 left-1/3 w-24 h-px bg-gradient-to-r from-transparent via-gold/20 to-transparent" />
      </div>

      {/* Content */}
      <div className="relative z-10 text-center px-6 max-w-5xl mx-auto">
        {/* Eyebrow */}
        <div className="flex items-center justify-center gap-4 mb-10 animate-fade-in">
          <div className="h-px w-16 bg-gradient-to-r from-transparent to-gold/60" />
          <span className="font-sans text-[0.65rem] tracking-widest3 uppercase text-gold/80">
            Est. Long Island · Since 2024
          </span>
          <div className="h-px w-16 bg-gradient-to-l from-transparent to-gold/60" />
        </div>

        {/* Main headline */}
        <h1 className="font-serif font-light text-ivory leading-none mb-6 animate-fade-up">
          <span className="block text-6xl sm:text-7xl lg:text-9xl tracking-tight">
            The Art of
          </span>
          <span className="block text-6xl sm:text-7xl lg:text-9xl tracking-tight italic text-gold/90 mt-1">
            Understated
          </span>
          <span className="block text-6xl sm:text-7xl lg:text-9xl tracking-tight">
            Luxury
          </span>
        </h1>

        {/* Subtitle */}
        <p className="font-sans font-light text-ivory/60 text-sm sm:text-base tracking-widest uppercase mt-10 mb-14 animate-fade-up-slow max-w-md mx-auto leading-relaxed">
          Coastal essentials crafted for those who<br />require no introduction
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 animate-fade-up-slow">
          <a href="#collections" className="btn-ghost">
            Explore Collections
          </a>
          <a href="#our-story" className="font-sans text-xs tracking-widest uppercase text-ivory/50 hover:text-gold/80 transition-colors duration-300">
            Our Heritage ↓
          </a>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3 animate-fade-in">
          <span className="font-sans text-[0.6rem] tracking-widest2 uppercase text-ivory/30">Scroll</span>
          <div className="w-px h-12 bg-gradient-to-b from-ivory/30 to-transparent" />
        </div>
      </div>
    </section>
  )
}

export default Hero
