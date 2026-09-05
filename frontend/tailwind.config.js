/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#07090D',
          900: '#0B0E13',
          850: '#0E1218',
          800: '#10141B',
          750: '#141A23',
          700: '#1A2230',
          600: '#243044',
        },
        line: '#1E2736',
        mist: {
          100: '#E8EDF5',
          200: '#C5CDD8',
          400: '#8B95A7',
          500: '#6B7385',
        },
        accent: {
          DEFAULT: '#7C6CFF',
          glow: '#9B8CFF',
          dim: '#4C3FD9',
        },
        verified: '#3EE0A3',
        review: '#F5A524',
        risk: '#F45B69',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        panel: '0 0 0 1px rgba(255,255,255,0.04), 0 24px 60px rgba(0,0,0,0.45)',
        lift: '0 0 0 1px rgba(124,108,255,0.18), 0 18px 40px rgba(0,0,0,0.35)',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { opacity: '0.45' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        pulseGlow: 'pulseGlow 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
