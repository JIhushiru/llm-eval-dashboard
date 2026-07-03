"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseApiResult<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

// Small client-side fetch hook: re-runs the fetcher when deps change,
// ignores stale responses, exposes a manual reload.
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fetcher);
  fnRef.current = fetcher;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fnRef.current().then(
      (d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      },
      (e: unknown) => {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
    // deps is caller-provided; fnRef always holds the latest fetcher
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { data, error, loading, reload };
}
