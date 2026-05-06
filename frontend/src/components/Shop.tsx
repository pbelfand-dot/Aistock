import React, { useState, useEffect, useRef } from 'react'

type Category = 'All' | 'Tops' | 'Bottoms' | 'Footwear'

interface Product {
  id: string
  name: string
  collection: string
  category: Exclude<Category, 'All'>
  material: string
  price: number
  colors: { name: string; hex: string }[]
  sizes: string[]
  tag?: string
  bg: string
  gradient: string
  textColor: string
  stripes?: boolean
}

const products: Product[] = [
  {
    id: 'jones-tee',
    name: 'Jones Beach Tee',
    collection: 'Drop 01',
    category: 'Tops',
    material: 'Heavyweight Cotton',
    price: 40,
    colors: [
      { name: 'Natural', hex: '#EDE8DC' },
    ],
    sizes: ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
    tag: 'Drop 01',
    bg: '#EDE8DC',
    gradient: 'from-[#EDE8DC] to-[#D4C5A9]',
    textColor: '#1B2A4A',
  },
  {
    id: 'jones-swim-short',
    name: 'Jones Beach Swim Short',
    collection: 'Drop 01',
    category: 'Bottoms',
    material: 'Custom Toile Print',
    price: 50,
    colors: [
      { name: 'Powder Blue', hex: '#A8C4D4' },
    ],
    sizes: ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
    tag: 'Signature',
    bg: '#A8C4D4',
    gradient: 'from-[#A8C4D4] to-[#7AAABF]',
    textColor: '#1B2A4A',
    stripes: true,
  },
  {
    id: 'linen-pant',
    name: 'Linen Beach Pant',
    collection: 'Essentials',
    category: 'Bottoms',
    material: 'Portuguese Linen',
    price: 80,
    colors: [
      { name: 'Ivory', hex: '#EDE8DC' },
      { name: 'Navy', hex: '#1B2A4A' },
      { name: 'Stone', hex: '#C4B89A' },
      { name: 'Charcoal', hex: '#3A3A3A' },
      { name: 'Oatmeal', hex: '#D4C5A9' },
    ],
    sizes: ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
    tag: 'Essentials',
    bg: '#D4C5A9',
    gradient: 'from-[#D4C5A9] to-[#B8A888]',
    textColor: '#2A2A2A',
  },
  {
    id: 'jones-sandal',
    name: 'Jones Beach Sandal',
    collection: 'Drop 01',
    category: 'Footwear',
    material: 'Full-Grain Leather',
    price: 130,
    colors: [
      { name: 'Espresso', hex: '#3D2B1A' },
    ],
    sizes: ['7', '8', '9', '10', '11', '12', '13'],
    tag: 'Limited',
    bg: '#3D2B1A',
    gradient: 'from-[#3D2B1A] to-[#5C3D20]',
    textColor: '#E8C99A',
  },
]

const categories: Category[] = ['All', 'Tops', 'Bottoms', 'Footwear']

const ProductCard: React.FC<{ product: Product }> = ({ product }) => {
  const [selectedColor, setSelectedColor] = useState(0)
  const [selectedSize, setSelectedSize] = useState<string | null>(null)
  const [added, setAdded] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); observer.disconnect() } },
      { threshold: 0.1 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const activeColor = product.colors[selectedColor]
  const isFootwear = product.category === 'Footwear'

  const handleAddToBag = () => {
    if (!selectedSize) return
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  return (
    <div ref={ref} className="animate-on-scroll group">
      {/* Image panel */}
      <div
        className="relative overflow-hidden mb-5 cursor-pointer"
        style={{ background: `linear-gradient(135deg, ${activeColor.hex}, ${activeColor.hex}cc)` }}
      >
        <div className="h-72 relative">
          {/* Stripe overlay for swim short */}
          {product.stripes && (
            <div
              className="absolute inset-0 opacity-35"
              style={{
                backgroundImage: `repeating-linear-gradient(90deg, #F5F0E8 0, #F5F0E8 26px, transparent 26px, transparent 52px)`,
              }}
            />
          )}
          {/* Woven texture */}
          <div
            className="absolute inset-0 opacity-[0.04]"
            style={{
              backgroundImage: `repeating-linear-gradient(0deg, #fff 0, #fff 1px, transparent 0, transparent 3px),
                repeating-linear-gradient(90deg, #fff 0, #fff 1px, transparent 0, transparent 3px)`,
            }}
          />
          {/* Tag */}
          {product.tag && (
            <div className="absolute top-4 left-4 z-10">
              <span
                className="font-sans text-[0.55rem] tracking-widest uppercase py-1 px-2.5 border"
                style={{
                  color: product.textColor,
                  borderColor: `${product.textColor}40`,
                  backgroundColor: `${activeColor.hex}80`,
                }}
              >
                {product.tag}
              </span>
            </div>
          )}
          {/* Product monogram */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-display text-8xl opacity-[0.06]" style={{ color: product.textColor }}>
              LI
            </span>
          </div>
          {/* Hover quick-view */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-all duration-500" />
        </div>
      </div>

      {/* Info */}
      <div>
        <div className="flex items-start justify-between mb-2">
          <div>
            <p className="font-sans text-[0.6rem] tracking-widest uppercase text-muted/60 mb-1">
              {product.material}
            </p>
            <h3 className="font-serif text-xl text-charcoal group-hover:text-navy transition-colors duration-300">
              {product.name}
            </h3>
          </div>
          <span className="font-serif text-xl text-navy ml-4 shrink-0">${product.price}</span>
        </div>

        {/* Color swatches */}
        {product.colors.length > 1 && (
          <div className="flex items-center gap-2 mt-3 mb-3">
            {product.colors.map((color, i) => (
              <button
                key={color.name}
                onClick={() => setSelectedColor(i)}
                title={color.name}
                className="w-5 h-5 rounded-full border-2 transition-all duration-200"
                style={{
                  backgroundColor: color.hex,
                  borderColor: selectedColor === i ? '#C9A84C' : 'transparent',
                  boxShadow: selectedColor === i ? '0 0 0 1px #C9A84C' : '0 0 0 1px #ccc',
                }}
              />
            ))}
            <span className="font-sans text-[0.6rem] text-muted ml-1">{activeColor.name}</span>
          </div>
        )}
        {product.colors.length === 1 && (
          <p className="font-sans text-xs text-muted mt-1 mb-3">{product.colors[0].name}</p>
        )}

        {/* Size selector */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {product.sizes.map(size => (
            <button
              key={size}
              onClick={() => setSelectedSize(size)}
              className={`font-sans text-[0.6rem] tracking-wide px-2.5 py-1.5 border transition-all duration-200 ${
                selectedSize === size
                  ? 'bg-navy text-ivory border-navy'
                  : 'bg-transparent text-muted border-sand hover:border-navy hover:text-navy'
              }`}
            >
              {size}
            </button>
          ))}
        </div>

        {/* Add to bag */}
        <button
          onClick={handleAddToBag}
          disabled={!selectedSize}
          className={`w-full py-3 font-sans text-[0.7rem] tracking-widest uppercase transition-all duration-300 ${
            added
              ? 'bg-forest text-ivory'
              : selectedSize
              ? 'bg-navy text-ivory hover:bg-gold hover:text-charcoal'
              : 'bg-sand/40 text-muted cursor-not-allowed'
          }`}
        >
          {added ? '✓ Added to Bag' : selectedSize ? 'Add to Bag' : `Select ${isFootwear ? 'Size' : 'Size'}`}
        </button>
      </div>
    </div>
  )
}

const Shop: React.FC = () => {
  const [activeCategory, setActiveCategory] = useState<Category>('All')
  const headerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = headerRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); observer.disconnect() } },
      { threshold: 0.2 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const filtered = activeCategory === 'All'
    ? products
    : products.filter(p => p.category === activeCategory)

  return (
    <section id="collections" className="py-24 bg-ivory">
      <div className="max-w-7xl mx-auto px-6 lg:px-12">

        {/* Header */}
        <div ref={headerRef} className="animate-on-scroll mb-14">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
            <div>
              <span className="font-sans text-[0.6rem] tracking-widest3 uppercase text-gold block mb-4">
                — Jones Beach · Drop 01 · Summer 2024 —
              </span>
              <h2 className="font-serif font-light text-5xl lg:text-6xl text-navy">
                Shop
              </h2>
            </div>

            {/* Category filters */}
            <div className="flex items-center gap-1">
              {categories.map(cat => (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  className={`font-sans text-[0.65rem] tracking-widest uppercase px-4 py-2 transition-all duration-300 ${
                    activeCategory === cat
                      ? 'bg-navy text-ivory'
                      : 'text-muted hover:text-navy border border-transparent hover:border-sand'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Count */}
          <div className="mt-6 pt-6 border-t border-sand/60 flex items-center justify-between">
            <p className="font-sans text-xs text-muted">
              {filtered.length} {filtered.length === 1 ? 'product' : 'products'}
            </p>
            <p className="font-sans text-[0.6rem] tracking-widest uppercase text-muted/60">
              Free shipping on orders over $150
            </p>
          </div>
        </div>

        {/* Product grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-14">
          {filtered.map(product => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>

        {/* Empty state */}
        {filtered.length === 0 && (
          <div className="text-center py-24 text-muted font-serif text-2xl italic">
            No products in this category yet.
          </div>
        )}
      </div>
    </section>
  )
}

export default Shop
