import { InputHTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

/**
 * Input Component
 * 
 * Reusable input component with validation states and error messages.
 * Follows design system specifications.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      helperText,
      leftIcon,
      rightIcon,
      className,
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;

    // Base input styles
    const baseStyles = 'w-full px-4 py-3 border rounded-button bg-white transition-all duration-200 focus:outline-none focus:ring-2 focus:border-transparent placeholder:text-text-muted disabled:bg-slate-50 disabled:cursor-not-allowed';

    // Error state styles
    const errorStyles = error
      ? 'border-danger-500 focus:ring-danger-500'
      : 'border-border focus:ring-primary-500 focus:border-primary-500';

    // Icon padding styles
    const paddingStyles = leftIcon ? 'pl-11' : rightIcon ? 'pr-11' : '';

    const inputStyles = twMerge(
      clsx(baseStyles, errorStyles, paddingStyles, className)
    );

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-text-primary mb-1"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={inputStyles}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 top-1/2 transform -translate-y-1/2 text-text-muted">
              {rightIcon}
            </div>
          )}
        </div>
        {error && (
          <p className="mt-1 text-sm text-danger-500">{error}</p>
        )}
        {helperText && !error && (
          <p className="mt-1 text-sm text-text-secondary">{helperText}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

/**
 * Textarea Component
 */
interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
  rows?: number;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helperText, rows = 4, className, id, ...props }, ref) => {
    const textareaId = id || `textarea-${Math.random().toString(36).substr(2, 9)}`;

    // Base textarea styles
    const baseStyles = 'w-full px-3 py-2 border rounded-button transition-all duration-200 focus:outline-none focus:ring-2 focus:border-transparent placeholder:text-text-muted disabled:bg-slate-50 disabled:cursor-not-allowed resize-none';

    // Error state styles
    const errorStyles = error
      ? 'border-danger-500 focus:ring-danger-500'
      : 'border-border focus:ring-primary-500 focus:border-primary-500';

    const textareaStyles = twMerge(clsx(baseStyles, errorStyles, className));

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-medium text-text-primary mb-1"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          rows={rows}
          className={textareaStyles}
          {...props}
        />
        {error && (
          <p className="mt-1 text-sm text-danger-500">{error}</p>
        )}
        {helperText && !error && (
          <p className="mt-1 text-sm text-text-secondary">{helperText}</p>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
