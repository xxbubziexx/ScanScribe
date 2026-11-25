import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const STORAGE_PREFIX = 'scanscribe_col_widths_';

function readStoredWidths<T extends string>(
  storageKey: string,
  defaults: Record<T, number>,
  minWidth: number
): Record<T, number> {
  const result = { ...defaults };
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return result;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object') return result;
    for (const key of Object.keys(defaults) as T[]) {
      const val = parsed[key];
      if (typeof val === 'number' && Number.isFinite(val) && val >= minWidth) {
        result[key] = Math.round(val);
      }
    }
  } catch {
    // Ignore storage access or malformed JSON errors and fall back to defaults
  }
  return result;
}

function persistWidths<T extends string>(storageKey: string, widths: Record<T, number>): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {
    // Ignore storage quota / privacy mode errors
  }
}

export interface ResizableColumnsResult<T extends string> {
  widths: Record<T, number>;
  totalWidth: number;
  isCustomized: boolean;
  activeCol: T | null;
  startResize: (col: T, e: React.MouseEvent<HTMLElement>) => void;
  resetColumn: (col: T) => void;
  resetAll: () => void;
}

export function useResizableColumns<T extends string>(
  tableKey: string,
  defaults: Record<T, number>,
  minWidth = 56
): ResizableColumnsResult<T> {
  const storageKey = `${STORAGE_PREFIX}${tableKey}`;
  const defaultsRef = useRef(defaults);
  defaultsRef.current = defaults;

  const [widths, setWidths] = useState<Record<T, number>>(() =>
    readStoredWidths(storageKey, defaults, minWidth)
  );
  const widthsRef = useRef(widths);
  widthsRef.current = widths;

  const [activeCol, setActiveCol] = useState<T | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, []);

  const totalWidth = useMemo(
    () => (Object.values(widths) as number[]).reduce((sum, w) => sum + w, 0),
    [widths]
  );

  const isCustomized = useMemo(
    () => (Object.keys(defaults) as T[]).some((key) => widths[key] !== defaults[key]),
    [widths, defaults]
  );

  const startResize = useCallback(
    (col: T, e: React.MouseEvent<HTMLElement>) => {
      e.preventDefault();
      e.stopPropagation();

      cleanupRef.current?.();

      const startX = e.clientX;
      const startWidth = widthsRef.current[col] ?? defaultsRef.current[col];
      const prevCursor = document.body.style.cursor;
      const prevUserSelect = document.body.style.userSelect;

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      setActiveCol(col);

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const delta = moveEvent.clientX - startX;
        const nextWidth = Math.max(minWidth, Math.round(startWidth + delta));
        const nextWidths = { ...widthsRef.current, [col]: nextWidth };
        widthsRef.current = nextWidths;
        setWidths(nextWidths);
      };

      const finish = () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', finish);
        document.body.style.cursor = prevCursor;
        document.body.style.userSelect = prevUserSelect;
        cleanupRef.current = null;
        setActiveCol(null);
        persistWidths(storageKey, widthsRef.current);
      };

      cleanupRef.current = () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', finish);
        document.body.style.cursor = prevCursor;
        document.body.style.userSelect = prevUserSelect;
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', finish);
    },
    [minWidth, storageKey]
  );

  const resetColumn = useCallback(
    (col: T) => {
      const nextWidths = { ...widthsRef.current, [col]: defaultsRef.current[col] };
      widthsRef.current = nextWidths;
      setWidths(nextWidths);
      persistWidths(storageKey, nextWidths);
    },
    [storageKey]
  );

  const resetAll = useCallback(() => {
    const fresh = { ...defaultsRef.current };
    widthsRef.current = fresh;
    setWidths(fresh);
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // Ignore storage access errors
    }
  }, [storageKey]);

  return {
    widths,
    totalWidth,
    isCustomized,
    activeCol,
    startResize,
    resetColumn,
    resetAll,
  };
}

export interface ColResizeHandleProps {
  col: string;
  label?: string;
  isActive?: boolean;
  onMouseDown: (e: React.MouseEvent<HTMLDivElement>) => void;
  onDoubleClick?: () => void;
}

export function ColResizeHandle({
  col,
  label,
  isActive = false,
  onMouseDown,
  onDoubleClick,
}: ColResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label ? `Resize ${label} column` : `Resize ${col} column`}
      title="Drag to resize • Double-click to reset"
      className={`ss-col-resizer${isActive ? ' ss-col-resizer--active' : ''}`}
      onMouseDown={(e) => {
        e.stopPropagation();
        onMouseDown(e);
      }}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDoubleClick?.();
      }}
    />
  );
}
