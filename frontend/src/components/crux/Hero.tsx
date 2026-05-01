import React, { useEffect, useRef } from 'react'
import * as THREE from 'three'

const Hero: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(canvas.clientWidth, canvas.clientHeight)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 1000)
    camera.position.set(0, 0, 30)

    // Chalk dust particles
    const PARTICLE_COUNT = 2000
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const velocities = new Float32Array(PARTICLE_COUNT * 3)
    const sizes = new Float32Array(PARTICLE_COUNT)
    const opacities = new Float32Array(PARTICLE_COUNT)

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 80
      positions[i * 3 + 1] = (Math.random() - 0.5) * 50
      positions[i * 3 + 2] = (Math.random() - 0.5) * 20
      velocities[i * 3] = (Math.random() - 0.5) * 0.02
      velocities[i * 3 + 1] = Math.random() * 0.03 + 0.005
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.01
      sizes[i] = Math.random() * 3 + 0.5
      opacities[i] = Math.random() * 0.6 + 0.1
    }

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))

    const mat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.15,
      transparent: true,
      opacity: 0.35,
      sizeAttenuation: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })

    const particles = new THREE.Points(geo, mat)
    scene.add(particles)

    // Mountain wireframe silhouette
    const mountainPts: THREE.Vector3[] = []
    const mountainShape = [
      [-20, -8, 0], [-12, -8, 0], [-8, 2, 0], [-5, -2, 0], [-2, 6, 0],
      [0, 10, 0], [2, 6, 0], [5, -2, 0], [8, 2, 0], [12, -8, 0], [20, -8, 0]
    ]
    mountainShape.forEach(([x, y, z]) => mountainPts.push(new THREE.Vector3(x, y, z)))

    const mountainGeo = new THREE.BufferGeometry().setFromPoints(mountainPts)
    const mountainMat = new THREE.LineBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.08,
    })
    const mountain = new THREE.Line(mountainGeo, mountainMat)
    mountain.position.set(0, -5, -5)
    scene.add(mountain)

    // Second, smaller mountain behind
    const mountain2Pts: THREE.Vector3[] = []
    const shape2 = [
      [-15, -6, 0], [-8, -6, 0], [-4, 4, 0], [-1, 1, 0], [1, 7, 0],
      [3, 1, 0], [6, 4, 0], [9, -6, 0], [15, -6, 0]
    ]
    shape2.forEach(([x, y, z]) => mountain2Pts.push(new THREE.Vector3(x, y, z)))
    const mountain2Geo = new THREE.BufferGeometry().setFromPoints(mountain2Pts)
    const mountain2Mat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.04 })
    const mountain2 = new THREE.Line(mountain2Geo, mountain2Mat)
    mountain2.position.set(8, -5, -10)
    scene.add(mountain2)

    // Grid floor
    const gridHelper = new THREE.GridHelper(80, 20, 0xffffff, 0xffffff)
    ;(gridHelper.material as THREE.Material).transparent = true
    ;(gridHelper.material as THREE.Material).opacity = 0.03
    gridHelper.position.y = -14
    scene.add(gridHelper)

    let frame = 0
    let animId: number

    const animate = () => {
      animId = requestAnimationFrame(animate)
      frame++

      const pos = geo.attributes.position.array as Float32Array
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        pos[i * 3] += velocities[i * 3]
        pos[i * 3 + 1] += velocities[i * 3 + 1]
        pos[i * 3 + 2] += velocities[i * 3 + 2]

        // Reset particles that drift out of bounds
        if (pos[i * 3 + 1] > 30) {
          pos[i * 3 + 1] = -25
          pos[i * 3] = (Math.random() - 0.5) * 80
        }
        if (Math.abs(pos[i * 3]) > 45) {
          pos[i * 3] = (Math.random() - 0.5) * 80
        }
      }
      geo.attributes.position.needsUpdate = true

      particles.rotation.y = Math.sin(frame * 0.0002) * 0.05
      mountain.rotation.y = Math.sin(frame * 0.0003) * 0.02
      mat.opacity = 0.3 + Math.sin(frame * 0.005) * 0.05

      renderer.render(scene, camera)
    }

    animate()

    const handleResize = () => {
      if (!canvas) return
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', handleResize)

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
      renderer.dispose()
      geo.dispose()
      mat.dispose()
    }
  }, [])

  return (
    <section className="relative h-screen flex items-center justify-center overflow-hidden bg-black">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        style={{ display: 'block' }}
      />

      {/* Gradient overlays */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-black pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-transparent to-black/60 pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 text-center px-6 max-w-5xl mx-auto">
        {/* Logo mark */}
        <div className="flex justify-center mb-8 animate-fade-in-up">
          <MountainLogo />
        </div>

        <p className="text-xs tracking-[0.5em] text-white/40 mb-4 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          CLIMB. CONQUER. EVOLVE.
        </p>

        <h1
          className="text-[clamp(3rem,10vw,8rem)] font-black tracking-tight text-white leading-none mb-6 animate-fade-in-up"
          style={{ animationDelay: '0.2s', fontFamily: 'system-ui', letterSpacing: '-0.04em' }}
        >
          CRUXED
        </h1>

        <p
          className="text-lg md:text-xl text-white/50 tracking-widest uppercase mb-12 animate-fade-in-up"
          style={{ animationDelay: '0.35s' }}
        >
          The Matterhorn Collection
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center animate-fade-in-up" style={{ animationDelay: '0.5s' }}>
          <a
            href="#products"
            className="px-10 py-4 bg-white text-black font-bold tracking-widest uppercase text-sm hover:bg-white/90 transition-all duration-300 hover:scale-105"
          >
            Shop Collection
          </a>
          <a
            href="#chalk-bag"
            className="px-10 py-4 border border-white/30 text-white font-bold tracking-widest uppercase text-sm hover:border-white/60 hover:bg-white/5 transition-all duration-300"
          >
            Explore Gear
          </a>
        </div>
      </div>

      {/* Scroll indicator */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 animate-bounce">
        <span className="text-xs tracking-[0.3em] text-white/30 uppercase">Scroll</span>
        <div className="w-px h-8 bg-gradient-to-b from-white/30 to-transparent" />
      </div>
    </section>
  )
}

const MountainLogo: React.FC = () => (
  <svg width="60" height="48" viewBox="0 0 60 48" fill="none">
    <path d="M30 2L2 46h56L30 2z" stroke="white" strokeWidth="1.5" fill="none" opacity="0.9" />
    <path d="M30 2L18 28L30 22L42 28L30 2z" fill="white" opacity="0.15" />
    <path d="M22 16L10 40h40L38 16L30 4L22 16z" stroke="white" strokeWidth="0.5" fill="none" opacity="0.3" />
  </svg>
)

export default Hero
