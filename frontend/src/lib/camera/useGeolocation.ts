import { useEffect, useState } from 'react';

export interface GeolocationState {
  coords: { latitude: number; longitude: number } | null;
  status: 'locating' | 'ready' | 'error';
  error: string | null;
}

/**
 * Drives Capture's top pill: "Locating…" while acquiring, "Location ready" once fixed.
 *
 * `enabled` gates the device-location request. Only camera capture needs the device's GPS;
 * a photo upload takes its location from the file's EXIF (or a manual restaurant search), so
 * Capture passes `enabled={mode === 'live'}` to avoid prompting for device location on upload.
 */
export function useGeolocation(enabled: boolean = true): GeolocationState {
  const [state, setState] = useState<GeolocationState>({ coords: null, status: 'locating', error: null });

  useEffect(() => {
    if (!enabled) {
      // Not in camera mode - never touch navigator.geolocation, so no permission prompt fires.
      setState({ coords: null, status: 'locating', error: null });
      return undefined;
    }
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
  }, [enabled]);

  return state;
}
