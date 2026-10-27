import { useEffect, useState } from "react";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

// Loads `load()` again whenever a dependency changes; a late answer to an older request is dropped.
export function useApi<T>(load: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let current = true;
    setState((previous) => ({ ...previous, loading: true }));
    load().then(
      (data) => current && setState({ data, error: null, loading: false }),
      (error: Error) => current && setState({ data: null, error: error.message, loading: false }),
    );
    return () => {
      current = false;
    };
  }, deps);
  return state;
}
