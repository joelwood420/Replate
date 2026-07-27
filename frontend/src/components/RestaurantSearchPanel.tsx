import { useEffect, useState } from 'react';
import { searchRestaurants, type RestaurantCandidate } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import styles from './RestaurantSearchPanel.module.css';

interface RestaurantSearchPanelProps {
  /** Soft ranking bias only - never becomes the job's location value. Only onSelect does that. */
  deviceCoords: { latitude: number; longitude: number } | null;
  onSelect: (restaurant: RestaurantCandidate) => void;
}

type SearchStatus = 'idle' | 'loading' | 'ready' | 'error';

export function RestaurantSearchPanel({ deviceCoords, onSelect }: RestaurantSearchPanelProps) {
  const { authHeaders } = useAuth();
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, 300);
  const [results, setResults] = useState<RestaurantCandidate[]>([]);
  const [status, setStatus] = useState<SearchStatus>('idle');

  useEffect(() => {
    if (debouncedQuery.trim().length < 2) {
      setResults([]);
      setStatus('idle');
      return undefined;
    }

    let cancelled = false;
    setStatus('loading');

    searchRestaurants(
      { query: debouncedQuery, latitude: deviceCoords?.latitude, longitude: deviceCoords?.longitude },
      authHeaders,
    )
      .then((response) => {
        if (cancelled) return;
        setResults(response.restaurants);
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, deviceCoords, authHeaders]);

  return (
    <div className={styles.panel}>
      <input
        className={styles.input}
        placeholder="Search for the restaurant…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      {status === 'loading' && <div className={styles.hint}>Searching…</div>}
      {status === 'error' && <div className={styles.hint}>Search unavailable. Try again.</div>}
      {status === 'ready' && results.length === 0 && <div className={styles.hint}>No matches found.</div>}
      <ul className={styles.results}>
        {results.map((restaurant) => (
          <li key={restaurant.place_id}>
            <button type="button" className={styles.resultRow} onClick={() => onSelect(restaurant)}>
              <span className={styles.resultName}>{restaurant.name}</span>
              <span className={styles.resultAddress}>{restaurant.address}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
