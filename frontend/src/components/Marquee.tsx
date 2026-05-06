import React from 'react'

const items = [
  'Linen · Portugal',
  'Hand-Stitched',
  'Sea Island Cotton',
  'Resort Luxury',
  'Long Island Heritage',
  'Timeless Design',
  'Limited Edition',
  'Coastal Refinement',
]

const Marquee: React.FC = () => {
  const repeated = [...items, ...items, ...items]

  return (
    <div className="bg-navy py-5 overflow-hidden">
      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-33.333%); }
        }
        .marquee-track {
          display: flex;
          width: max-content;
          animation: marquee 30s linear infinite;
        }
      `}</style>
      <div className="marquee-track">
        {repeated.map((item, i) => (
          <span key={i} className="flex items-center">
            <span className="font-sans text-[0.65rem] tracking-widest2 uppercase text-ivory/70 whitespace-nowrap px-8">
              {item}
            </span>
            <span className="text-gold/40 text-xs">✦</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export default Marquee
