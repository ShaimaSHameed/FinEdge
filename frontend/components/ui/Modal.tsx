'use client';

import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib';

type ModalSize = 'lg' | 'xl' | '4xl' | '6xl';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  size?: ModalSize;
  children: ReactNode;
}

const SIZE_CLASSES: Record<ModalSize, string> = {
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
  '4xl': 'max-w-6xl',
  '6xl': 'max-w-7xl',
};

export function Modal({
  open,
  onClose,
  title,
  description,
  size = 'xl',
  children,
}: ModalProps) {
  useEffect(() => {
    if (!open) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 md:p-6">
      <button
        type="button"
        aria-label="Close modal"
        className="absolute inset-0 bg-slate-950/60 backdrop-blur-[2px]"
        onClick={onClose}
      />

      <div
        className={cn(
          'relative z-[121] flex max-h-[90vh] w-full flex-col overflow-hidden rounded-[28px] border border-slate-200 bg-main-bg shadow-[0_32px_80px_rgba(15,23,42,0.32)]',
          SIZE_CLASSES[size]
        )}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby={description ? 'modal-description' : undefined}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5">
          <div>
            <h2 id="modal-title" className="text-2xl font-semibold text-text-primary">
              {title}
            </h2>
            {description && (
              <p id="modal-description" className="mt-1 text-sm text-text-secondary">
                {description}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200 bg-white text-text-secondary transition-colors duration-200 hover:bg-slate-50 hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-6 py-6">
          {children}
        </div>
      </div>
    </div>
  );
}
