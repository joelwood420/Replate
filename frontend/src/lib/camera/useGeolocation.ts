import { useEffect, useState } from 'react';

export interface GeolocationState {
  coords: { latitude: number; longitude: number } | null;
  status: 'locating' | 'ready' | 'error';
  error: string | null;
}

/** Drives Capture's top pill: "Locating…" while acquiring, "Location ready" once fixed. */
export function useGeolocation(): GeolocationState {
  const [state, setState] = useState<GeolocationState>({ coords: null, status: 'locating', error: null });

  useEffect(() => {
    if (!navigator.geolocation) {
      setState({ coords: null, status: 'error', error: 'Geolocation is not supported on this device.' });
      return undefined;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        setState({
          coords: { latitude: position.coords.latitude, longitude: position.coords.longitude },
          status: 'ready',
          error: null,
        });
      },
      (err) => {
        setState({ coords: null, status: 'error', error: err.message });
      },
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 },
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  return state;
}
