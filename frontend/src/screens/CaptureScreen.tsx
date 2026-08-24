import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { CaptureViewfinder } from '../components/CaptureViewfinder';
import { ErrorState } from '../components/ErrorState';
import { IconCamera, IconClose, IconFlipCamera, IconLibrary } from '../components/icons';
import { RestaurantSearchPanel } from '../components/RestaurantSearchPanel';
import {
  createJob,
  markUploadComplete,
  uploadPhotoToBlob,
  type CreateJobInput,
  type SelectedRestaurant,
} from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useCamera } from '../lib/camera/useCamera';
import { useExifLocation, type ExifLocationState } from '../lib/camera/useExifLocation';
import { useGeolocation } from '../lib/camera/useGeolocation';
import styles from './CaptureScreen.module.css';

type CaptureMode = 'live' | 'uploaded';

function isSubmitEnabled(
  mode: CaptureMode,
  geoCoords: { latitude: number; longitude: number } | null,
  exifStatus: ExifLocationState['status'],
  selectedRestaurant: SelectedRestaurant | null,
): boolean {
  if (mode === 'live') return geoCoords !== null;
  if (exifStatus === 'found') return true;
  if (exifStatus === 'not_found') return selectedRestaurant !== null;
  return false; // 'idle' | 'checking'
}

export function CaptureScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const { authHeaders } = useAuth();
  // A photo handed over from Home's "Upload a photo instead" action. Read once at
  // mount so the screen opens straight into uploaded mode with the camera dark.
  const initialUpload = (location.state as { uploadedFile?: File } | null)?.uploadedFile ?? null;

  const [mode, setMode] = useState<CaptureMode>(initialUpload ? 'uploaded' : 'live');
  const [uploadedPhoto, setUploadedPhoto] = useState<File | null>(initialUpload);

  // The live viewfinder only runs in live mode; an upload session never prompts for camera access.
  const { videoRef, isReady, error: cameraError, flipCamera, capturePhoto } = useCamera(mode === 'live');
  const geolocation = useGeolocation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadedPhotoUrl, setUploadedPhotoUrl] = useState<string | null>(null);
  const [selectedRestaurant, setSelectedRestaurant] = useState<SelectedRestaurant | null>(null);
  const exifLocation = useExifLocation(uploadedPhoto);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastShotUrl, setLastShotUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!uploadedPhoto) {
      setUploadedPhotoUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(uploadedPhoto);
    setUploadedPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadedPhoto]);

  function handleLibraryClick() {
    fileInputRef.current?.click();
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setSubmitError(null);
    setSelectedRestaurant(null);
    setMode('uploaded');
    setUploadedPhoto(file);
  }

  function handleUseCameraInstead() {
    setMode('live');
    setUploadedPhoto(null);
    setSelectedRestaurant(null);
    setSubmitError(null);
  }

  function buildCreateJobInput(): CreateJobInput | null {
    if (mode === 'live') {
      return geolocation.coords
        ? { latitude: geolocation.coords.latitude, longitude: geolocation.coords.longitude }
        : null;
    }
    if (exifLocation.status === 'found' && exifLocation.coords) {
      return { latitude: exifLocation.coords.latitude, longitude: exifLocation.coords.longitude };
    }
    if (exifLocation.status === 'not_found' && selectedRestaurant) {
      return { selected_restaurant: selectedRestaurant };
    }
    return null;
  }

  async function handleSubmit() {
    if (isSubmitting) return;
    const input = buildCreateJobInput();
    if (!input) return;

    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const photo = mode === 'live' ? await capturePhoto() : uploadedPhoto;
      if (!photo) throw new Error('Could not get a photo. Try again.');
      if (mode === 'live') setLastShotUrl(URL.createObjectURL(photo));

      const { job_id: jobId, upload_url: uploadUrl } = await createJob(input, authHeaders);
      await uploadPhotoToBlob(uploadUrl, photo);
      // Only now is the photo actually there for the pipeline to read.
      await markUploadComplete(jobId, authHeaders);
      navigate(`/jobs/${jobId}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
      setIsSubmitting(false);
    }
  }

  if (cameraError) {
    return <ErrorState message={cameraError} onRetry={() => window.location.reload()} />;
  }

  const submitEnabled = isSubmitEnabled(mode, geolocation.coords, exifLocation.status, selectedRestaurant);
  const showSearchPanel = mode === 'uploaded' && exifLocation.status === 'not_found';

  const hint =
    submitError ??
    (mode === 'live'
      ? geolocation.status === 'error'
        ? (geolocation.error ?? 'Location unavailable')
        : 'Center the dish in frame'
      : exifLocation.status === 'checking'
        ? 'Checking photo for a location…'
        : exifLocation.status === 'found'
          ? 'Location found in photo'
          : 'Ready to submit');

  const locationLabel =
    mode === 'live'
      ? geolocation.status === 'ready'
        ? 'Location ready'
        : 'Locating restaurant…'
      : exifLocation.status === 'checking'
        ? 'Checking photo…'
        : exifLocation.status === 'found'
          ? 'Location found'
          : 'Search for restaurant';

  return (
    <div className={styles.screen}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelected}
        className={styles.hiddenFileInput}
      />

      {mode === 'uploaded' && uploadedPhotoUrl ? (
        <img src={uploadedPhotoUrl} alt="" className={styles.video} />
      ) : (
        <video ref={videoRef} className={styles.video} autoPlay playsInline muted />
      )}
      {mode === 'live' && !isReady && <div className={styles.videoPlaceholder} />}

      <div className={styles.topBar}>
        <button type="button" className={styles.iconButton} onClick={() => navigate(-1)} aria-label="Close">
          <IconClose />
        </button>
        <div className={styles.locationPill}>
          <span className={styles.locationDot} />
          <span>{locationLabel}</span>
        </div>
        {mode === 'live' ? (
          <button type="button" className={styles.iconButton} onClick={flipCamera} aria-label="Flip camera">
            <IconFlipCamera />
          </button>
        ) : (
          <button
            type="button"
            className={styles.iconButton}
            onClick={handleUseCameraInstead}
            aria-label="Use camera instead"
          >
            <IconCamera />
          </button>
        )}
      </div>

      {mode === 'live' && <CaptureViewfinder />}

      <div className={styles.bottomBar}>
        {showSearchPanel ? (
          <>
            <RestaurantSearchPanel deviceCoords={geolocation.coords} onSelect={setSelectedRestaurant} />
            {selectedRestaurant && (
              <div className={styles.controls}>
                <span className={styles.hint}>{selectedRestaurant.name}</span>
                <button
                  type="button"
                  className={styles.shutter}
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  aria-label="Submit photo"
                >
                  <span className={styles.shutterInner} />
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <div className={styles.hint}>{hint}</div>
            <div className={styles.controls}>
              <div className={styles.lastShot}>
                {mode === 'live' && lastShotUrl && <img src={lastShotUrl} alt="" className={styles.lastShotImg} />}
                {mode === 'uploaded' && uploadedPhotoUrl && (
                  <img src={uploadedPhotoUrl} alt="" className={styles.lastShotImg} />
                )}
              </div>
              <button
                type="button"
                className={styles.shutter}
                onClick={handleSubmit}
                disabled={isSubmitting || !submitEnabled}
                aria-label={mode === 'live' ? 'Capture photo' : 'Submit photo'}
              >
                <span className={styles.shutterInner} />
              </button>
              {mode === 'live' ? (
                <button type="button" className={styles.flipButton} onClick={flipCamera} aria-label="Flip camera">
                  <IconFlipCamera size={20} />
                </button>
              ) : (
                <button
                  type="button"
                  className={styles.flipButton}
                  onClick={handleLibraryClick}
                  aria-label="Choose a different photo"
                >
                  <IconLibrary size={20} />
                </button>
              )}
            </div>
          </>
        )}
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
