'use client';

import { ExternalLink, ChevronRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui';
import { VerdictBadge } from '@/components/ui';
import type { InfluentialArticle } from '@/types';
import { useState } from 'react';

/**
 * InfluentialArticleCard Component
 * 
 * Displays influential articles with expandable details and external link.
 */
interface InfluentialArticleCardProps {
  articles: InfluentialArticle[];
}

export function InfluentialArticleCard({ articles }: InfluentialArticleCardProps) {
  const [expandedArticle, setExpandedArticle] = useState<string | null>(null);

  const toggleExpand = (title: string) => {
    setExpandedArticle(expandedArticle === title ? null : title);
  };

  if (articles.length === 0) {
    return (
      <Card>
        <CardContent>
          <p className="text-center text-text-secondary py-8">
            No influential articles available
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Influential Articles</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {articles.map((article, index) => (
            <div key={index} className="border border-border rounded-lg overflow-hidden">
              {/* Article Header */}
              <div 
                className="p-4 bg-white cursor-pointer hover:bg-slate-50 transition-colors"
                onClick={() => toggleExpand(article.title)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h5 className="font-semibold text-text-primary flex-1 pr-4">
                    {article.title}
                  </h5>
                  <div className="flex items-center gap-3">
                    <VerdictBadge verdict={article.verdict} />
                    <span className={`text-sm font-semibold px-2 py-1 rounded ${
                      article.sentiment > 0 
                        ? 'bg-success-100 text-success-900' 
                        : article.sentiment < 0 
                          ? 'bg-danger-100 text-danger-900' 
                          : 'bg-slate-100 text-slate-700'
                    }`}>
                      {article.sentiment.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="text-sm text-text-secondary space-y-1">
                  <p>Source: {article.source}</p>
                </div>
              </div>

              {/* Expandable Reasoning */}
              {expandedArticle === article.title && (
                <div className="p-4 bg-slate-50 border-t border-border">
                  <h6 className="text-sm font-semibold text-text-primary mb-2">
                    Reasoning
                  </h6>
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {article.reasoning}
                  </p>
                  
                  {/* External Link */}
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 font-medium mt-3 transition-colors"
                    >
                      Read Full Article
                      <ExternalLink size={16} />
                    </a>
                  )}
                </div>
              )}

              {/* Expand/Collapse Indicator */}
              <div 
                className="px-4 py-2 bg-white border-t border-border flex items-center justify-center cursor-pointer hover:bg-slate-50 transition-colors"
                onClick={() => toggleExpand(article.title)}
              >
                {expandedArticle === article.title ? (
                  <span className="text-sm text-text-secondary">Show Less</span>
                ) : (
                  <div className="flex items-center gap-1 text-sm text-text-secondary">
                    <span>Read More</span>
                    <ChevronRight size={16} />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
