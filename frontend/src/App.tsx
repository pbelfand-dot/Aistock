import React from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Marquee from './components/Marquee'
import Shop from './components/Shop'
import Story from './components/Story'
import Craftsmanship from './components/Craftsmanship'
import Newsletter from './components/Newsletter'
import Footer from './components/Footer'

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-ivory">
      <Navbar />
      <Hero />
      <Marquee />
      <Shop />
      <Story />
      <Craftsmanship />
      <Newsletter />
      <Footer />
    </div>
  )
}

export default App
