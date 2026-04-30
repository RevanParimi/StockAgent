/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand:   { DEFAULT:'#2563EB', light:'#3B82F6', soft:'#EFF6FF', pale:'#DBEAFE' },
        surface: { DEFAULT:'#FFFFFF', muted:'#F8FAFF' },
        verdict: {
          'strong-buy':'#15803D', 'buy':'#16A34A',
          'neutral':'#B45309',
          'sell':'#C2410C',    'strong-sell':'#DC2626',
        },
      },
      fontFamily: {
        sans: ['Inter','system-ui','sans-serif'],
        mono: ['JetBrains Mono','monospace'],
      },
      boxShadow: {
        card:       '0 2px 16px rgba(37,99,235,0.07), 0 1px 3px rgba(0,0,0,0.05)',
        'card-up':  '0 8px 32px rgba(37,99,235,0.12)',
      },
      animation: {
        'slide-up': 'slideUp 0.45s cubic-bezier(0.16,1,0.3,1) both',
        'fade-in':  'fadeIn 0.4s ease both',
        'ticker':   'ticker 30s linear infinite',
      },
      keyframes: {
        slideUp: { from:{opacity:'0',transform:'translateY(18px)'}, to:{opacity:'1',transform:'translateY(0)'} },
        fadeIn:  { from:{opacity:'0'}, to:{opacity:'1'} },
        ticker:  { from:{transform:'translateX(0)'}, to:{transform:'translateX(-50%)'} },
      },
    },
  },
  plugins: [],
}
