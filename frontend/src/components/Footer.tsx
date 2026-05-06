import React from 'react'

const Footer: React.FC = () => {
  const links = {
    Collections: ['The Newport', 'The Montauk', 'The Gatsby', 'Archive'],
    Company: ['Our Story', 'Craftsmanship', 'Sustainability', 'Press'],
    Client: ['Size Guide', 'Care Instructions', 'Returns', 'Contact'],
  }

  return (
    <footer id="contact" className="bg-charcoal text-ivory/70">
      {/* Top footer */}
      <div className="max-w-7xl mx-auto px-6 lg:px-12 pt-20 pb-12">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-12 mb-16">
          {/* Brand column */}
          <div className="md:col-span-2">
            <div className="mb-6">
              <div className="font-display text-3xl text-ivory tracking-widest3 mb-1">L.I.</div>
              <div className="font-sans text-[0.55rem] tracking-widest2 uppercase text-tan">Beachwear</div>
            </div>
            <p className="font-sans font-light text-sm text-ivory/40 leading-relaxed mb-8 max-w-xs">
              Coastal luxury for those who understand that true elegance
              needs no announcement.
            </p>
            {/* Social links */}
            <div className="flex items-center gap-5">
              {['Instagram', 'Pinterest', 'Twitter'].map(social => (
                <a
                  key={social}
                  href="#"
                  className="font-sans text-[0.6rem] tracking-widest uppercase text-ivory/30 hover:text-gold transition-colors duration-300"
                >
                  {social}
                </a>
              ))}
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(links).map(([category, items]) => (
            <div key={category}>
              <h4 className="font-sans text-[0.6rem] tracking-widest2 uppercase text-gold/70 mb-5">
                {category}
              </h4>
              <ul className="space-y-3">
                {items.map(item => (
                  <li key={item}>
                    <a
                      href="#"
                      className="font-sans font-light text-sm text-ivory/40 hover:text-ivory/80 transition-colors duration-300"
                    >
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Divider */}
        <div className="h-px bg-ivory/10 mb-10" />

        {/* Contact info */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
          {[
            { label: 'Atelier', value: 'Long Island, New York' },
            { label: 'Email', value: 'hello@libeachwear.com' },
            { label: 'Telephone', value: '+1 (631) 000 0000' },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="font-sans text-[0.6rem] tracking-widest uppercase text-gold/50 mb-1">{label}</p>
              <p className="font-sans text-sm text-ivory/50">{value}</p>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="h-px bg-ivory/5 mb-8" />
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="font-sans text-[0.6rem] tracking-wide text-ivory/20">
            © 2024 L.I. Beachwear. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            {['Privacy Policy', 'Terms of Service', 'Cookie Policy'].map(item => (
              <a
                key={item}
                href="#"
                className="font-sans text-[0.6rem] tracking-wide text-ivory/20 hover:text-ivory/50 transition-colors duration-300"
              >
                {item}
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer
