import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CaptureViewfinder } from '../components/CaptureViewfinder';
import { ErrorState } from '../components/ErrorState';
import { createJob, uploadPhotoToBlob } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useCamera } from '../lib/camera/useCamera';
import { useGeolocation } from '../lib/camera/useGeolocation';
import styles from './CaptureScreen.module.css';

export function CaptureScreen() {
  const navigate = useNavigate();
  const { authHeaders } = useAuth();
  const { videoRef, isReady, error: cameraError, flipCamera, capturePhoto } = useCamera();
  const geolocation = useGeolocation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastShotUrl, setLastShotUrl] = useState<string | null>(null);

  async function handleShutter() {
    if (isSubmitting || !geolocation.coords) return;
    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const photo = await capturePhoto();
      if (!photo) throw new Error('Could not capture a photo. Try again.');
      setLastShotUrl(URL.createObjectURL(photo));

      const { job_id: jobId, upload_url: uploadUrl } = await createJob(
        { latitude: geolocation.coords.latitude, longitude: geolocation.coords.longitude },
        authHeaders,
      );
      await uploadPhotoToBlob(uploadUrl, photo);
      navigate(`/jobs/${jobId}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
      setIsSubmitting(false);
    }
  }

  if (cameraError) {
    return <ErrorState message={cameraError} onRetry={() => window.location.reload()} />;
  }

  const hint =
    submitError ??
    (geolocation.status === 'error'
      ? (geolocation.error ?? 'Location unavailable')
      : 'Center the dish in frame');
  const locationLabel = geolocation.status === 'ready' ? 'Location ready' : 'Locating restaurant…';

  return (
    <div className={styles.screen}>
      <video ref={videoRef} className={styles.video} autoPlay playsInline muted />
      {!isReady && <div className={styles.videoPlaceholder} />}

      <div className={styles.topBar}>
        <button type="button" className={styles.iconButton} onClick={() => navigate(-1)} aria-label="Close">
          ×
        </button>
        <div className={styles.locationPill}>
          <span className={styles.locationDot} />
          <span>{locationLabel}</span>
        </div>
        <button type="button" className={styles.iconButton} onClick={flipCamera} aria-label="Flip camera">
          ⟳
        </button>
      </div>

      <CaptureViewfinder />

      <div className={styles.bottomBar}>
        <div className={styles.hint}>{hint}</div>
        <div className={styles.controls}>
          <div className={styles.lastShot}>
            {lastShotUrl && <img src={lastShotUrl} alt="" className={styles.lastShotImg} />}
          </div>
          <button
            type="button"
            className={styles.shutter}
            onClick={handleShutter}
            disabled={isSubmitting || !geolocation.coords}
            aria-label="Capture photo"
          >
            <span className={styles.shutterInner} />
          </button>
          <button type="button" className={styles.flipButton} onClick={flipCamera} aria-label="Flip camera">
            ⇄
          </button>
        </div>
      </div>
    </div>
  );
}
