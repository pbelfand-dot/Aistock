import React from 'react'
import Navbar from './components/crux/Navbar'
import Hero from './components/crux/Hero'
import BrandSection from './components/crux/BrandSection'
import ProductCarousel from './components/crux/ProductCarousel'
import ShirtSection from './components/crux/ShirtSection'
import Footer from './components/crux/Footer'
import { PRODUCTS } from './data/products'

const App: React.FC = () => {
  const slidedProducts = PRODUCTS.filter(p => p.splitSlides)
  const shirtProduct = PRODUCTS.find(p => !p.splitSlides)!

  return (
    <div className="bg-black min-h-screen">
      <Navbar />
      <Hero />
      <BrandSection />

      {/* Products with per-color slides */}
      {slidedProducts.map(product => (
        <ProductCarousel key={product.id} product={product} />
      ))}

      {/* Shirt — full multi-color showcase, no per-color slides */}
      <ShirtSection product={shirtProduct} />

      <Footer />
    </div>
  )
}

export default App
