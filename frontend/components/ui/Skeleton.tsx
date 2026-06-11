import { HTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
  animation?: 'pulse' | 'wave' | 'none';
}

/**
 * Skeleton Component
 * 
 * Loading placeholder component for various UI elements.
 * Provides visual feedback during content loading.
 */
export const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(
  (
    {
      variant = 'text',
      width,
      height,
      animation = 'pulse',
      className,
      ...props
    },
    ref
  ) => {
    // Base styles
    const baseStyles = 'bg-slate-200';

    // Variant styles
    const variantStyles: Record<string, string> = {
      text: 'h-4 w-full rounded',
      circular: 'rounded-full',
      rectangular: 'rounded-md',
    };

    // Animation styles
    const animationStyles: Record<string, string> = {
      pulse: 'animate-pulse',
      wave: 'animate-shimmer',
      none: '',
    };

    const skeletonStyles = clsx(
      baseStyles,
      variantStyles[variant],
      animationStyles[animation],
      className
    );

    const inlineStyles: React.CSSProperties = {
      width: width,
      height: height,
    };

    return (
      <div
        ref={ref}
        className={skeletonStyles}
        style={inlineStyles}
        {...props}
      />
    );
  }
);

Skeleton.displayName = 'Skeleton';

/**
 * Card Skeleton Component
 * For loading card placeholders
 */
export const CardSkeleton = () => {
  return (
    <div className="bg-card-bg rounded-card shadow-card p-6">
      <div className="flex items-start justify-between mb-4">
        <Skeleton variant="text" width="120px" />
        <Skeleton variant="rectangular" width="60px" height="24px" />
      </div>
      <div className="space-y-3">
        <Skeleton variant="text" width="80%" />
        <Skeleton variant="text" width="60%" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <Skeleton variant="text" width="100%" />
        <Skeleton variant="text" width="100%" />
      </div>
      <div className="mt-4 flex gap-2">
        <Skeleton variant="rectangular" width="80px" height="28px" />
        <Skeleton variant="rectangular" width="80px" height="28px" />
      </div>
    </div>
  );
};

/**
 * Table Skeleton Component
 * For loading table rows
 */
interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

export const TableSkeleton = ({ rows = 5, columns = 4 }: TableSkeletonProps) => {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-4 items-center">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton
              key={colIndex}
              variant="text"
              width={colIndex === 0 ? '120px' : '100%'}
              className="flex-1"
            />
          ))}
        </div>
      ))}
    </div>
  );
};

/**
 * Loading Spinner Component
 */
interface LoadingSpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg';
  color?: string;
}

export const LoadingSpinner = forwardRef<HTMLDivElement, LoadingSpinnerProps>(
  ({ size = 'md', color = 'text-primary-600', className, ...props }, ref) => {
    const sizeStyles: Record<string, string> = {
      sm: 'w-4 h-4',
      md: 'w-8 h-8',
      lg: 'w-12 h-12',
    };

    return (
      <div ref={ref} className={`flex items-center justify-center ${className}`} {...props}>
        <svg
          className={`animate-spin ${sizeStyles[size]} ${color}`}
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      </div>
    );
  }
);

LoadingSpinner.displayName = 'LoadingSpinner';

/**
 * Loading Overlay Component
 * Full-screen loading overlay
 */
interface LoadingOverlayProps {
  message?: string;
}

export const LoadingOverlay = ({ message = 'Loading...' }: LoadingOverlayProps) => {
  return (
    <div className="fixed inset-0 bg-white/80 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="flex flex-col items-center gap-4">
        <LoadingSpinner size="lg" />
        <p className="text-text-secondary">{message}</p>
      </div>
    </div>
  );
};
