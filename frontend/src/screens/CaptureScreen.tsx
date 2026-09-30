import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CaptureViewfinder } from '../components/CaptureViewfinder';
import { ErrorState } from '../components/ErrorState';
import { IconClose, IconFlipCamera } from '../components/icons';
import { createJob, markUploadComplete, uploadPhotoToBlob, type CreateJobInput } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useCamera } from '../lib/camera/useCamera';
import { useGeolocation } from '../lib/camera/useGeolocation';
import styles from './CaptureScreen.module.css';

/**
 * Camera-only capture. Photo uploads have their own screen (UploadScreen) so this one never
 * has to reason about an uploaded file, EXIF, or a manual restaurant search - a live capture
 * always uses the device's GPS. See docs/decisions.md.
 */
export function CaptureScreen() {
  const navigate = useNavigate();
  const { authHeaders } = useAuth();
  const { videoRef, isReady, error: cameraError, flipCamera, capturePhoto } = useCamera(true);
  const geolocation = useGeolocation();

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastShotUrl, setLastShotUrl] = useState<string | null>(null);

  function buildCreateJobInput(): CreateJobInput | null {
    return geolocation.coords
      ? { latitude: geolocation.coords.latitude, longitude: geolocation.coords.longitude }
      : null;
  }

  async function handleSubmit() {
    if (isSubmitting) return;
    const input = buildCreateJobInput();
    if (!input) return;

    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const photo = await capturePhoto();
      if (!photo) throw new Error('Could not get a photo. Try again.');
      setLastShotUrl(URL.createObjectURL(photo));

      const { job_id: jobId, upload_url: uploadUrl } = await createJob(input, authHeaders);
      await uploadPhotoToBlob(uploadUrl, photo);
      // Only now is the photo actually there for the pipeline to read.
      const uploaded = await markUploadComplete(jobId, authHeaders);
      // The food pre-check answers in about a second. Show a non-food photo right now,
      // while the diner still has the phone out and the plate in front of them.
      if (uploaded.failure_code === 'not_food') {
        navigate(`/jobs/${jobId}`, { replace: true });
        return;
      }
      // Land in the cookbook, where the dish is already saved and processes in place. This
      // avoids the "sit and wait" feeling of a dedicated processing screen: the scan is
      // captured, it's in your cookbook, you can put your phone away. Replace so Back from
      // the cookbook doesn't return to the camera.
      navigate('/cookbook', { replace: true });
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
      setIsSubmitting(false);
    }
  }

  if (cameraError) {
    return <ErrorState message={cameraError} onRetry={() => window.location.reload()} />;
  }

  const submitEnabled = geolocation.coords !== null;

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
          <IconClose />
        </button>
        <div className={styles.locationPill}>
          <span className={styles.locationDot} />
          <span>{locationLabel}</span>
        </div>
        <button type="button" className={styles.iconButton} onClick={flipCamera} aria-label="Flip camera">
          <IconFlipCamera />
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
            onClick={handleSubmit}
            disabled={isSubmitting || !submitEnabled}
            aria-label="Capture photo"
          >
            <span className={styles.shutterInner} />
          </button>
          <button type="button" className={styles.flipButton} onClick={flipCamera} aria-label="Flip camera">
            <IconFlipCamera size={20} />
          </button>
        </div>
      </div>

      {isSubmitting && (
        <div className={styles.sendingOverlay} role="status" aria-live="polite">
          <span className={styles.sendingSpinner} aria-hidden="true" />
          <span className={styles.sendingText}>Sending your dish…</span>
        </div>
      )}
    </div>
  );
}
