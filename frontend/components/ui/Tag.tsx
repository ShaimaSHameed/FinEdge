import { HTMLAttributes, forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type TagVariant = 'default' | 'success' | 'danger' | 'warning' | 'info' | 'neutral';
export type TagSize = 'sm' | 'md' | 'lg';

interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: TagVariant;
  size?: TagSize;
  children: React.ReactNode;
}

/**
 * Tag Component
 * 
 * Reusable tag/pill component following design system:
 * - Exchange tags: Light Grey BG with Dark Grey text
 * - Sector tags: Light Purple BG (#F3E8FF) with Purple text (#7E22CE)
 * - Sentiment pills: Green text/Green BG for positive, Red for negative
 */
export const Tag = forwardRef<HTMLSpanElement, TagProps>(
  ({ variant = 'default', size = 'md', className, children, ...props }, ref) => {
    // Base styles
    const baseStyles = 'inline-flex items-center justify-center font-medium rounded-full';

    // Variant styles
    const variantStyles: Record<TagVariant, ClassValue> = {
      default: 'bg-slate-100 text-slate-700',
      success: 'bg-success-100 text-success-900',
      danger: 'bg-danger-100 text-danger-900',
      warning: 'bg-amber-100 text-amber-900',
      info: 'bg-blue-100 text-blue-900',
      neutral: 'bg-slate-100 text-slate-700',
    };

    // Size styles
    const sizeStyles: Record<TagSize, ClassValue> = {
      sm: 'px-2 py-0.5 text-xs',
      md: 'px-2.5 py-0.5 text-sm',
      lg: 'px-3 py-1 text-base',
    };

    const tagStyles = twMerge(
      clsx(baseStyles, variantStyles[variant], sizeStyles[size], className)
    );

    return (
      <span ref={ref} className={tagStyles} {...props}>
        {children}
      </span>
    );
  }
);

Tag.displayName = 'Tag';

/**
 * Exchange Tag Component
 * For displaying stock exchange information
 */
interface ExchangeTagProps extends HTMLAttributes<HTMLSpanElement> {
  exchange: string;
}

export const ExchangeTag = forwardRef<HTMLSpanElement, ExchangeTagProps>(
  ({ exchange, className, ...props }, ref) => {
    const exchangeStyles = twMerge(
      clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        'bg-slate-100 text-slate-700',
        className
      )
    );

    return (
      <span ref={ref} className={exchangeStyles} {...props}>
        {exchange}
      </span>
    );
  }
);

ExchangeTag.displayName = 'ExchangeTag';

/**
 * Sector Tag Component
 * For displaying sector information with purple styling
 */
interface SectorTagProps extends HTMLAttributes<HTMLSpanElement> {
  sector: string;
}

export const SectorTag = forwardRef<HTMLSpanElement, SectorTagProps>(
  ({ sector, className, ...props }, ref) => {
    const sectorStyles = twMerge(
      clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        'bg-purple-100 text-purple-700',
        className
      )
    );

    return (
      <span ref={ref} className={sectorStyles} {...props}>
        {sector}
      </span>
    );
  }
);

SectorTag.displayName = 'SectorTag';

/**
 * Sentiment Pill Component
 * For displaying sentiment status
 */
interface SentimentPillProps extends HTMLAttributes<HTMLSpanElement> {
  sentiment: 'Positive' | 'Negative' | 'Neutral';
}

export const SentimentPill = forwardRef<HTMLSpanElement, SentimentPillProps>(
  ({ sentiment, className, ...props }, ref) => {
    const sentimentStyles: Record<string, ClassValue> = {
      Positive: 'bg-success-100 text-success-900',
      Negative: 'bg-danger-100 text-danger-900',
      Neutral: 'bg-slate-100 text-slate-700',
    };

    const pillStyles = twMerge(
      clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        sentimentStyles[sentiment],
        className
      )
    );

    return (
      <span ref={ref} className={pillStyles} {...props}>
        {sentiment}
      </span>
    );
  }
);

SentimentPill.displayName = 'SentimentPill';

/**
 * Verdict Badge Component
 * For displaying BUY/SELL/HOLD verdicts
 */
interface VerdictBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  verdict: 'BUY' | 'SELL' | 'HOLD';
}

export const VerdictBadge = forwardRef<HTMLSpanElement, VerdictBadgeProps>(
  ({ verdict, className, ...props }, ref) => {
    const verdictStyles: Record<string, ClassValue> = {
      BUY: 'bg-success-500 text-white',
      SELL: 'bg-danger-500 text-white',
      HOLD: 'bg-slate-500 text-white',
    };

    const badgeStyles = twMerge(
      clsx(
        'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase',
        verdictStyles[verdict],
        className
      )
    );

    return (
      <span ref={ref} className={badgeStyles} {...props}>
        {verdict}
      </span>
    );
  }
);

VerdictBadge.displayName = 'VerdictBadge';
