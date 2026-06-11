import { Suspense } from 'react';
import StockAnalysisPage from '@/components/pages/analyze/StockAnalysisPage';

export default function AnalyzePage() {
  return (
    <Suspense fallback={null}>
      <StockAnalysisPage />
    </Suspense>
  );
}
