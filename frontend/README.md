# FinEdge Frontend

AI-Powered Stock Market Intelligence Platform - Frontend Application

## Tech Stack

- **Framework:** Next.js 14.x with App Router
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **State Management:** Zustand
- **HTTP Client:** Axios
- **Forms:** react-hook-form + zod
- **Charts:** Recharts
- **Icons:** Lucide React

## Project Structure

```
frontend/
├── app/                      # Next.js App Router pages
│   ├── (auth)/             # Authentication pages
│   ├── dashboard/           # Dashboard page
│   ├── analyze/             # Analysis input page
│   ├── results/             # Analysis results page
│   ├── history/             # Analysis history page
│   ├── profile/             # User profile page
│   ├── layout.tsx           # Root layout
│   ├── page.tsx             # Home page
│   └── globals.css          # Global styles
├── components/               # Reusable components
│   ├── ui/                 # Base UI components
│   ├── charts/              # Chart components
│   ├── analysis/            # Analysis-specific components
│   └── layout/             # Layout components
├── lib/                     # Utility functions
│   ├── api.ts               # API client
│   └── utils.ts             # Helper functions
├── stores/                  # Zustand stores
│   ├── authStore.ts         # Authentication state
│   ├── sentimentStore.ts    # Sentiment analysis state
│   └── index.ts            # Store exports
├── types/                   # TypeScript type definitions
│   ├── sentiment.ts          # Sentiment types
│   ├── auth.ts              # Auth types
│   └── index.ts             # Type exports
├── public/                  # Static assets
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── next.config.js
└── .env.example
```

## Getting Started

### Prerequisites

- Node.js 18.x or higher
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create environment file:
```bash
cp .env.example .env
```

3. Configure environment variables in `.env`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=FinEdge
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

4. Run development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000) in your browser

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run format` - Format code with Prettier

## Design System

### Colors

| Color | Hex | Usage |
|--------|------|-------|
| Primary Blue | `#2563EB` | Primary buttons, Logo icon |
| Sidebar Navy | `#0F172A` | Sidebar background |
| Main BG | `#F8FAFC` | Main content background |
| Card White | `#FFFFFF` | Card backgrounds |
| Success Green | `#10B981` | Positive sentiment, bullish signals |
| Danger Red | `#EF4444` | Negative sentiment, alerts |
| Text Primary | `#1E293B` | Headings, prices, symbols |
| Text Secondary | `#64748B` | Labels, metadata |
| Border | `#E2E8F0` | Dividers, borders |

### Typography

- **Font Family:** Inter
- **Weights:** 400 (Regular), 500 (Medium), 600 (Semi-Bold), 700 (Bold)

## API Integration

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze/sentimental` | Analyze sentiment |
| GET | `/api/user/history` | Get analysis history |
| DELETE | `/api/user/history/{id}` | Delete history item |
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/logout` | User logout |
| GET | `/api/user/profile` | Get user profile |
| PUT | `/api/user/profile` | Update user profile |
| GET | `/api/health` | Health check |

## State Management

### Auth Store
- User session
- JWT token
- Authentication status
- Loading states
- Error handling

### Sentiment Store
- Current analysis state
- Analysis results
- Analysis history
- Loading states
- Error handling

## Features

### Authentication
- User login/logout
- User registration
- JWT token management
- Session persistence

### Sentiment Analysis
- Ticker search
- Market selection (US/IN)
- Real-time sentiment analysis
- News breakdown visualization
- Trend charts
- Influential articles display

### Dashboard
- Stock tiles with sentiment indicators
- Sparkline charts
- Market data display
- Re-analyze functionality

### History
- Analysis history (last 50)
- Search and filter
- Delete history items
- View past analyses

### Profile
- User information display
- Account settings
- Password change
- Usage statistics

## Performance Targets

- Page load time: <3 seconds
- Time to Interactive: <5 seconds
- First Contentful Paint: <1.5 seconds
- API response time (cached): <2 seconds

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Deployment

### Build for Production

```bash
npm run build
```

### Start Production Server

```bash
npm start
```

## License

This project is part of the FinEdge platform.
