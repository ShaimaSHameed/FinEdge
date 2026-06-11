import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Primary Action Blue
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563EB', // Primary Action Blue
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        // Sidebar Dark Navy
        sidebar: {
          bg: '#0F172A', // Dark Navy
          bgDark: '#020617', // Darker Navy
          text: '#94A3B8', // Idle state text
          textActive: '#FFFFFF', // Active state text
        },
        // Main Background
        main: {
          bg: '#F8FAFC', // Off-White
        },
        // Card Background
        card: {
          bg: '#FFFFFF', // White
        },
        // Success/Bullish Green
        success: {
          50: '#f0fdf4',
          100: '#dcfce7', // Background Pills
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#10B981', // Success/Bullish Green Text
        },
        // Danger/Error Red
        danger: {
          50: '#fef2f2',
          100: '#fee2e2',
          200: '#fecaca',
          300: '#fca5a5',
          400: '#f87171',
          500: '#ef4444', // Alert Red
          600: '#dc2626',
          700: '#b91c1c',
          800: '#991b1b',
          900: '#7f1d1d',
        },
        // Neutral/Text
        text: {
          primary: '#1E293B', // Headings
          secondary: '#64748B', // Labels, Meta-data
          muted: '#94A3B8',
        },
        // Border/Divider
        border: '#E2E8F0',
      },
      fontFamily: {
        sans: ['var(--font-jakarta)', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1rem' }],
        'sm': ['0.875rem', { lineHeight: '1.25rem' }],
        'base': ['1rem', { lineHeight: '1.5rem' }],
        'lg': ['1.125rem', { lineHeight: '1.75rem' }],
        'xl': ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
      },
      fontWeight: {
        regular: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
      },
      borderRadius: {
        'card': '16px',
        'button': '999px',
      },
      boxShadow: {
        'card': '0 1px 2px rgba(15, 23, 42, 0.04)',
        'card-hover': '0 18px 48px -28px rgba(15, 23, 42, 0.35)',
      },
    },
  },
  plugins: [],
}

export default config
