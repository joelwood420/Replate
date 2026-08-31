import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

export type FacingMode = 'environment' | 'user';

export interface CameraState {
  videoRef: RefObject<HTMLVideoElement>;
  isReady: boolean;
  error: string | null;
  facingMode: FacingMode;
  flipCamera: () => void;
  capturePhoto: () => Promise<Blob | null>;
}

/**
 * Live in-app viewfinder via getUserMedia, per the Capture design (not an OS-camera
 * handoff). `enabled` gates the camera so an upload-only session never prompts for
 * camera access; it starts the moment the caller flips to live mode.
 */
export function useCamera(enabled = true): CameraState {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [facingMode, setFacingMode] = useState<FacingMode>('environment');
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      // Release any stream from a previous live session and stay dark.
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setIsReady(false);
      return undefined;
    }

    let cancelled = false;
    setIsReady(false);

    async function start() {
      try {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        // Ask for a portrait-oriented stream so the viewfinder's `object-fit: cover`
        // barely has to crop. With no hint the phone hands back its native landscape
        // frame, which cover then scales up to fill the tall screen, cropping the sides
        // hard - that crop reads as the camera being "zoomed in". All ideal (never
        // exact) so a device without a rear camera or these exact dimensions still
        // starts rather than throwing OverconstrainedError.
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1080 },
            height: { ideal: 1920 },
          },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setIsReady(true);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Unable to access the camera.');
      }
    }

    void start();

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [facingMode, enabled]);

  const flipCamera = useCallback(() => {
    setFacingMode((mode) => (mode === 'environment' ? 'user' : 'environment'));
  }, []);

  const capturePhoto = useCallback(async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return null;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.9);
    });
  }, []);

  return { videoRef, isReady, error, facingMode, flipCamera, capturePhoto };
}
