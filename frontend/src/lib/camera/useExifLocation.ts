import { useEffect, useState } from 'react';
import { gps } from 'exifr';

export interface ExifLocationState {
  status: 'idle' | 'checking' | 'found' | 'not_found';
  coords: { latitude: number; longitude: number } | null;
}

/**
 * Parses GPS EXIF from an uploaded photo File. `not_found` covers both "no
 * GPS tags present" and "EXIF unreadable" (corrupt/stripped/screenshot) -
 * per the decision log, both cases fall through to manual restaurant search.
 */
export function useExifLocation(file: File | null): ExifLocationState {
  const [state, setState] = useState<ExifLocationState>({ status: 'idle', coords: null });

  useEffect(() => {
    if (!file) {
      setState({ status: 'idle', coords: null });
      return undefined;
    }

    let cancelled = false;
    setState({ status: 'checking', coords: null });

    gps(file)
      .then((result) => {
        if (cancelled) return;
        if (result && typeof result.latitude === 'number' && typeof result.longitude === 'number') {
          setState({ status: 'found', coords: { latitude: result.latitude, longitude: result.longitude } });
        } else {
          setState({ status: 'not_found', coords: null });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'not_found', coords: null });
      });

    return () => {
      cancelled = true;
    };
  }, [file]);

  return state;
}
