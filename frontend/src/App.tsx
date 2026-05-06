import React from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Marquee from './components/Marquee'
import Collections from './components/Collections'
import Story from './components/Story'
import Craftsmanship from './components/Craftsmanship'
import Featured from './components/Featured'
import Newsletter from './components/Newsletter'
import Footer from './components/Footer'

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-ivory">
      <Navbar />
      <Hero />
      <Marquee />
      <Collections />
      <Story />
      <Craftsmanship />
      <Featured />
      <Newsletter />
      <Footer />
    </div>
  )
}

export default App
