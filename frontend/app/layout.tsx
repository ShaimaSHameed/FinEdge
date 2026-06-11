import type { Metadata } from 'next';
import { Plus_Jakarta_Sans } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/layout';
import { MainContent } from '@/components/layout';

const jakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-jakarta',
});

export const metadata: Metadata = {
  title: 'FinEdge - Market Intelligence Platform',
  description: 'AI-powered stock market analysis for Indian and US markets',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={jakarta.variable}>
      <body>
        <div className="flex min-h-screen bg-white">
          <Sidebar />
          <MainContent>{children}</MainContent>
        </div>
      </body>
    </html>
  );
}
