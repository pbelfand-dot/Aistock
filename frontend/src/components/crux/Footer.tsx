import React from 'react'

const Footer: React.FC = () => (
  <footer className="bg-black border-t border-white/5 py-16">
    <div className="max-w-7xl mx-auto px-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-12">
        {/* Brand */}
        <div className="md:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <svg width="32" height="26" viewBox="0 0 60 48" fill="none">
              <path d="M30 2L2 46h56L30 2z" stroke="white" strokeWidth="1.5" fill="none" />
              <path d="M30 2L18 28L30 22L42 28L30 2z" fill="white" opacity="0.15" />
            </svg>
            <span className="text-white font-black text-xl tracking-tighter">CRUXED</span>
          </div>
          <p className="text-white/25 text-xs leading-relaxed max-w-xs">
            Inspired by the world's most iconic peak. Built for those who seek more.
            For the obsessed. For the driven. For those who climb.
          </p>
          <p className="text-white/15 text-xs mt-4 tracking-widest uppercase">
            CRUXED IS MORE THAN GEAR. IT'S A MINDSET.
          </p>
        </div>

        <div>
          <p className="text-white/20 text-xs tracking-widest uppercase mb-4">Collection</p>
          {['The Matterhorn Chalk Bag', 'Ridge Pants', 'Ankle Sock', 'Technical Overshirt'].map(item => (
            <p key={item} className="text-white/40 text-xs mb-2 hover:text-white cursor-pointer transition-colors">
              {item}
            </p>
          ))}
        </div>

        <div>
          <p className="text-white/20 text-xs tracking-widest uppercase mb-4">Info</p>
          {['Size Guide', 'Care Instructions', 'Materials', 'Contact'].map(item => (
            <p key={item} className="text-white/40 text-xs mb-2 hover:text-white cursor-pointer transition-colors">
              {item}
            </p>
          ))}
        </div>
      </div>

      <div className="border-t border-white/5 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
        <p className="text-white/15 text-xs tracking-wider">
          © 2025 CRUXED. BUILT FOR THE OBSESSED.
        </p>
        <p className="text-white/10 text-xs tracking-widest uppercase">
          CLIMB. CONQUER. EVOLVE.
        </p>
      </div>
    </div>
  </footer>
)

export default Footer
