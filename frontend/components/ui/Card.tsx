import { HTMLAttributes, forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'bordered';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

/**
 * Card Component
 * 
 * Reusable card component following design system:
 * - 12px border-radius
 * - Subtle shadow (0 1px 3px rgba(0,0,0,0.1))
 * - 24px padding (default)
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      variant = 'default',
      padding = 'md',
      className,
      children,
      ...props
    },
    ref
  ) => {
    // Base styles
    const baseStyles = 'bg-card-bg rounded-card';

    // Variant styles
    const variantStyles: Record<string, ClassValue> = {
      default: 'border border-slate-200 shadow-card',
      elevated: 'border border-slate-200 shadow-card-hover',
      bordered: 'border border-border shadow-none',
    };

    // Padding styles
    const paddingStyles: Record<string, ClassValue> = {
      none: 'p-0',
      sm: 'p-4',
      md: 'p-6',
      lg: 'p-8',
    };

    const cardStyles = twMerge(
      clsx(baseStyles, variantStyles[variant], paddingStyles[padding], className)
    );

    return (
      <div ref={ref} className={cardStyles} {...props}>
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

/**
 * Card Header Component
 */
interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ className, children, ...props }, ref) => {
    const headerStyles = twMerge(
      clsx('mb-4 pb-4 border-b border-border last:border-0', className)
    );

    return (
      <div ref={ref} className={headerStyles} {...props}>
        {children}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

/**
 * Card Title Component
 */
interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  children: React.ReactNode;
}

export const CardTitle = forwardRef<HTMLHeadingElement, CardTitleProps>(
  ({ className, children, ...props }, ref) => {
    const titleStyles = twMerge(
      clsx('text-lg font-semibold text-text-primary', className)
    );

    return (
      <h3 ref={ref} className={titleStyles} {...props}>
        {children}
      </h3>
    );
  }
);

CardTitle.displayName = 'CardTitle';

/**
 * Card Content Component
 */
interface CardContentProps extends HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const CardContent = forwardRef<HTMLDivElement, CardContentProps>(
  ({ className, children, ...props }, ref) => {
    const contentStyles = twMerge(clsx('text-text-primary', className));

    return (
      <div ref={ref} className={contentStyles} {...props}>
        {children}
      </div>
    );
  }
);

CardContent.displayName = 'CardContent';

/**
 * Card Footer Component
 */
interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ className, children, ...props }, ref) => {
    const footerStyles = twMerge(
      clsx('mt-4 pt-4 border-t border-border flex items-center gap-2', className)
    );

    return (
      <div ref={ref} className={footerStyles} {...props}>
        {children}
      </div>
    );
  }
);

CardFooter.displayName = 'CardFooter';
