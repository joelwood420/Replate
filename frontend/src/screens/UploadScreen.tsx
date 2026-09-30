import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ErrorState } from '../components/ErrorState';
import { IconClose } from '../components/icons';
import { PillButton } from '../components/PillButton';
import { RestaurantSearchPanel } from '../components/RestaurantSearchPanel';
import {
  createJob,
  markUploadComplete,
  uploadPhotoToBlob,
  type CreateJobInput,
  type SelectedRestaurant,
} from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useExifLocation } from '../lib/camera/useExifLocation';
import styles from './UploadScreen.module.css';

/**
 * The upload flow, deliberately separate from CaptureScreen: no camera and no device
 * geolocation. An uploaded photo takes its location from its own EXIF GPS; when the photo
 * carries none, the user searches for the restaurant so the menu match still has something
 * to match against. See docs/decisions.md.
 */
export function UploadScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const { authHeaders } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // A photo handed over from Home's "Upload a photo" action. Read once at mount; the user
  // can still replace it here.
  const initialFile = (location.state as { uploadedFile?: File } | null)?.uploadedFile ?? null;
  const [photo, setPhoto] = useState<File | null>(initialFile);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [selectedRestaurant, setSelectedRestaurant] = useState<SelectedRestaurant | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const exifLocation = useExifLocation(photo);

  useEffect(() => {
    if (!photo) {
      setPhotoUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(photo);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  // A new photo invalidates a restaurant picked for the previous one.
  useEffect(() => {
    setSelectedRestaurant(null);
    setSubmitError(null);
  }, [photo]);

  function handlePickClick() {
    fileInputRef.current?.click();
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) setPhoto(file);
  }

  function buildCreateJobInput(): CreateJobInput | null {
    if (exifLocation.status === 'found' && exifLocation.coords) {
      return { latitude: exifLocation.coords.latitude, longitude: exifLocation.coords.longitude };
    }
    if (exifLocation.status === 'not_found' && selectedRestaurant) {
      return { selected_restaurant: selectedRestaurant };
    }
    return null;
  }

  async function handleSubmit() {
    if (isSubmitting || !photo) return;
    const input = buildCreateJobInput();
    if (!input) return;

    setSubmitError(null);
    setIsSubmitting(true);
    try {
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
      // Land in the cookbook, where the dish is already saved and processes in place, rather
      // than on a dedicated processing screen. Replace so Back doesn't return to the upload form.
      navigate('/cookbook', { replace: true });
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
      setIsSubmitting(false);
    }
  }

  // No photo yet (e.g. navigated here directly): offer a picker rather than a dead screen.
  if (!photo) {
    return (
      <>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileSelected}
          className={styles.hiddenFileInput}
        />
        <ErrorState
          tone="notice"
          title="Upload a photo"
          message="Choose a photo of your dish and we'll identify it."
          primaryAction={{ label: 'Choose a photo', onClick: handlePickClick }}
          secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home') }}
        />
      </>
    );
  }

  const submitEnabled =
    exifLocation.status === 'found' ||
    (exifLocation.status === 'not_found' && selectedRestaurant !== null);

  return (
    <div className={styles.screen}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelected}
        className={styles.hiddenFileInput}
      />

      <div className={styles.topBar}>
        <button type="button" className={styles.iconButton} onClick={() => navigate('/home')} aria-label="Close">
          <IconClose size={18} />
        </button>
        <span className={styles.topTitle}>Upload a photo</span>
        <span className={styles.topSpacer} />
      </div>

      <div className={styles.body}>
        <div className={styles.photoFrame}>
          {photoUrl && <img src={photoUrl} alt="Your dish" className={styles.photo} />}
        </div>

        {exifLocation.status === 'checking' && (
          <div className={styles.statusRow}>
            <span className={styles.dot} aria-hidden="true" />
            Checking your photo for a location…
          </div>
        )}

        {exifLocation.status === 'found' && (
          <div className={`${styles.statusRow} ${styles.statusFound}`}>
            <span className={styles.check} aria-hidden="true" />
            We found where this was taken.
          </div>
        )}

        {exifLocation.status === 'not_found' && (
          <div className={styles.searchBlock}>
            <div className={styles.searchLabel}>This photo has no location — which restaurant was it?</div>
            <RestaurantSearchPanel deviceCoords={null} onSelect={setSelectedRestaurant} />
          </div>
        )}

        {submitError && <div className={styles.error}>{submitError}</div>}
      </div>

      <div className={styles.footer}>
        <PillButton variant="cta" onClick={handleSubmit} disabled={isSubmitting || !submitEnabled}>
          {isSubmitting ? 'Uploading…' : 'Scan this dish'}
        </PillButton>
        <button type="button" className={styles.secondary} onClick={handlePickClick} disabled={isSubmitting}>
          Choose a different photo
        </button>
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
