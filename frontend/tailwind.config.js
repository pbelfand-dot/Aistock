/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ivory: '#F5F0E8',
        cream: '#EDE8DC',
        sand: '#D4C5A9',
        linen: '#F2EBE0',
        parchment: '#E8DFD0',
        navy: {
          DEFAULT: '#1B2A4A',
          light: '#2C3E60',
          dark: '#111C33',
        },
        forest: {
          DEFAULT: '#2C3E2D',
          light: '#3D5C3E',
          dark: '#1A2A1B',
        },
        gold: {
          DEFAULT: '#C9A84C',
          light: '#D4B86A',
          dark: '#A8882E',
          pale: '#E8D9A8',
        },
        tan: {
          DEFAULT: '#8B7355',
          light: '#A08B6B',
          dark: '#6E5B40',
        },
        charcoal: '#2A2A2A',
        muted: '#6B6B5A',
      },
      fontFamily: {
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
        display: ['Playfair Display SC', 'Georgia', 'serif'],
        sans: ['Jost', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.8s ease-in-out',
        'fade-up': 'fadeUp 0.9s ease-out',
        'fade-up-slow': 'fadeUp 1.2s ease-out',
        'shimmer': 'shimmer 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeUp: {
          '0%': { transform: 'translateY(30px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        shimmer: {
          '0%, 100%': { opacity: '0.6' },
          '50%': { opacity: '1' },
        },
      },
      letterSpacing: {
        widest2: '0.3em',
        widest3: '0.4em',
      },
    },
  },
  plugins: [],
}
