import { useCallback, useEffect, useRef, useState } from "react";

const cache = new Map();

export function useApi(fetcher, deps = [], options = {}) {
  const { cacheKey } = options;
  const [data, setData] = useState(cacheKey ? cache.get(cacheKey) : undefined);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(data === undefined);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetcherRef.current();
      setData(response.data);
      if (cacheKey) cache.set(cacheKey, response.data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, refetch: load };
}
