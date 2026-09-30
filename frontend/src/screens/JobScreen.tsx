import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ComponentCard } from '../components/ComponentCard';
import { ErrorState } from '../components/ErrorState';
import { IngredientRow } from '../components/IngredientRow';
import { MethodStep } from '../components/MethodStep';
import { PillButton } from '../components/PillButton';
import { ProcessingOrb, type OrbStage } from '../components/ProcessingOrb';
import { RecipeHero } from '../components/RecipeHero';
import { IconBack } from '../components/icons';
import { cancelJob, deleteJob, reverseEngineerJob } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { formatQuantity, timeAgo } from '../lib/format';
import { useJobsStore } from '../lib/jobs/JobsProvider';
import { useJobPolling } from '../lib/jobs/useJobPolling';
import styles from './JobScreen.module.css';

function ProcessingShell({ stage = 'identify' }: { stage?: OrbStage }) {
  return (
    <div className={styles.processingScreen}>
      <ProcessingOrb stage={stage} />
    </div>
  );
}

// The identify-stage waiting screen, reached by tapping a still-processing dish in the
// cookbook: a plain near-black field with just the orb and copy that makes leaving feel safe
// (no photo behind it). The back arrow returns to the cookbook and keeps the scan running
// there; Cancel stops it outright.
function ScanningOverlay({
  isCancelling,
  cancelError,
  onCancel,
  onBack,
}: {
  isCancelling: boolean;
  cancelError: string | null;
  onCancel: () => void;
  onBack: () => void;
}) {
  return (
    <div className={styles.scanOverlay}>
      <button type="button" className={styles.scanClose} onClick={onBack} aria-label="Back to cookbook">
        <IconBack size={18} />
      </button>
      <div className={styles.scanContent}>
        <ProcessingOrb stage="identify" />
        <p className={styles.scanHint}>
          This usually takes under a minute. You can leave — we’ll keep it in your cookbook.
        </p>
        {cancelError && <p className={styles.scanError}>{cancelError}</p>}
        <button type="button" className={styles.scanCancel} onClick={onCancel} disabled={isCancelling}>
          {isCancelling ? 'Cancelling…' : 'Cancel scan'}
        </button>
      </div>
    </div>
  );
}

// The backend has no structured error code: a moderation rejection lands in `Failed`
// with error_message = "This photo was rejected by image moderation (...)" (see
// backend/activities/moderate_image.py). Detecting it by that signature lets us swap in
// kinder, non-accusatory copy and never surface the raw category list to the diner.
function isModerationRejection(message: string | undefined): boolean {
  return !!message && message.toLowerCase().includes('image moderation');
}

export function JobScreen() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { authHeaders } = useAuth();
  const { job, error, isLoading, refetch } = useJobPolling(jobId);
  const { removeJob } = useJobsStore();
  const [isDeleting, setIsDeleting] = useState(false);
  const [isStartingRecipe, setIsStartingRecipe] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  // Which component's recipe to show; null shows the full dish (every component combined).
  const [selectedComponent, setSelectedComponent] = useState<number | null>(null);

  // A different dish means the previous component selection no longer applies.
  useEffect(() => {
    setSelectedComponent(null);
  }, [job?.job_id]);

  async function handleDelete() {
    if (!jobId || isDeleting) return;
    setIsDeleting(true);
    try {
      await deleteJob(jobId, authHeaders);
      removeJob(jobId);
      navigate('/cookbook');
    } catch {
      // Leave the screen as-is on failure; the dish still exists, so the user can retry.
      setIsDeleting(false);
    }
  }

  async function handleCancel() {
    if (!jobId || isCancelling) return;
    setIsCancelling(true);
    setCancelError(null);
    try {
      await cancelJob(jobId, authHeaders);
      // The job is now terminal (Cancelled); re-read so the screen leaves the
      // processing state and polling stops.
      refetch();
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : 'Could not cancel this scan.');
    } finally {
      setIsCancelling(false);
    }
  }

  async function handleReverseEngineer() {
    if (!jobId || isStartingRecipe) return;
    setIsStartingRecipe(true);
    setStartError(null);
    try {
      await reverseEngineerJob(jobId, authHeaders);
      // The job has moved from the terminal Identified state back into flight, so
      // polling has to be restarted to see it reach Completed.
      refetch();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Could not start reverse engineering.');
    } finally {
      setIsStartingRecipe(false);
    }
  }

  if (error) {
    return (
      <ErrorState
        title="Something went wrong"
        message="We couldn't load this dish just now. It's usually a quick hiccup."
        onRetry={refetch}
        secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home') }}
      />
    );
  }

  if (isLoading || !job) {
    return <ProcessingShell />;
  }

  if (job.status === 'Failed' && job.failure_code === 'not_food') {
    return (
      <ErrorState
        tone="moderation"
        title="That doesn't look like food"
        // The backend always sends its own wording (shared/models.NOT_FOOD_MESSAGE or the
        // vision model's reason); this fallback only covers a job missing one.
        message={job.error_message ?? 'Try again with a photo of your plate.'}
        primaryAction={{ label: 'Take another photo', onClick: () => navigate('/capture', { replace: true }) }}
        secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home', { replace: true }) }}
      />
    );
  }

  if (job.status === 'Failed') {
    const moderation = isModerationRejection(job.error_message);
    return (
      <ErrorState
        tone={moderation ? 'moderation' : 'error'}
        title={moderation ? "Let's try a different shot" : "That scan didn't work"}
        message={
          moderation
            ? 'We couldn’t use this photo. Aim for the dish itself — the plate front and centre, in good light — and snap it again.'
            : 'We couldn’t identify this one, and it’s usually the photo. Get the whole plate in frame, in good light, and give it another go.'
        }
        primaryAction={{ label: 'Take another photo', onClick: () => navigate('/capture', { replace: true }) }}
        secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home', { replace: true }) }}
      />
    );
  }

  if (job.status === 'Cancelled') {
    return (
      <ErrorState
        tone="notice"
        title="Scan cancelled"
        message="You stopped this scan, so nothing was charged for it. Take another whenever you're ready."
        primaryAction={{ label: 'Take another photo', onClick: () => navigate('/capture', { replace: true }) }}
        secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home', { replace: true }) }}
      />
    );
  }

  // Stage 1 (identify) shows the just-captured photo with the orb over it and a Cancel
  // control, so the user can wait, leave (the dish keeps processing in their cookbook), or
  // stop it to halt model spend. Stage 2 (Generating) is the user-initiated recipe build —
  // it keeps the heavier full-screen "generate" treatment and is not cancellable here.
  if (job.status === 'Queued' || job.status === 'Processing') {
    return (
      <ScanningOverlay
        isCancelling={isCancelling}
        cancelError={cancelError}
        onCancel={handleCancel}
        onBack={() => navigate('/cookbook')}
      />
    );
  }

  if (job.status === 'Generating') {
    return <ProcessingShell stage="generate" />;
  }

  const { result } = job;
  if (!result) {
    return (
      <ErrorState
        title="That came back empty"
        message="This dish finished processing but didn’t return anything to cook. Scanning it again usually fixes it."
        primaryAction={{ label: 'Take another photo', onClick: () => navigate('/capture', { replace: true }) }}
        secondaryAction={{ label: 'Back to home', onClick: () => navigate('/home', { replace: true }) }}
      />
    );
  }

  const awaitingRecipe = job.status === 'Identified';
  // With nothing selected the dish shows in full: every component's ingredients as one
  // list plus every component's method. Clicking a component focuses both the ingredients
  // and the method to just that component; clicking it again restores the full dish.
  const shownElements =
    selectedComponent === null ? result.elements : [result.elements[selectedComponent]];
  // Per-component method headings only earn their place on a genuinely multi-component
  // dish; a single-component dish is just one numbered list with nothing to disambiguate.
  const showComponentHeadings = result.elements.length > 1;
  const restaurantMeta = `${result.restaurant_name ?? 'Unknown restaurant'} · identified ${timeAgo(job.created_at)}`;
  // A failed generation reverts the job to Identified and records why, so the error
  // shows inline next to a button the user can press again.
  const recipeError = startError ?? (awaitingRecipe ? job.error_message : undefined);

  return (
    <div className={styles.screen}>
      <div className={styles.scrollArea}>
        <RecipeHero
          imageUrl={job.image_url}
          dishName={result.dish_name ?? 'Your dish'}
          restaurantMeta={restaurantMeta}
          matchMethod={result.match_method}
          mode="cookbook"
          onBack={() => navigate(-1)}
          onDelete={handleDelete}
          isDeleting={isDeleting}
        />

        {awaitingRecipe ? (
          <div className={styles.reverseEngineerPrompt}>
            <p className={styles.promptBody}>
              We know what this dish is. Reverse engineer it to get the ingredients and
              method for every component.
            </p>
            {recipeError && <div className={styles.promptError}>{recipeError}</div>}
          </div>
        ) : (
          <>
            <div className={styles.section}>
              <div className={styles.sectionLabel}>The Components</div>
              <div className={styles.componentsGrid}>
                {result.elements.map((element, index) => (
                  <ComponentCard
                    key={element.name}
                    role={element.role}
                    name={element.name}
                    selected={selectedComponent === index}
                    onClick={() =>
                      setSelectedComponent((current) => (current === index ? null : index))
                    }
                  />
                ))}
              </div>
            </div>

            <div className={styles.section}>
              <div className={styles.sectionLabel}>Ingredients</div>
              <div className={styles.ingredientsList}>
                {shownElements.flatMap((element) =>
                  element.ingredients.map((ingredient, index) => (
                    <IngredientRow
                      key={`${element.name}-${index}`}
                      name={ingredient.ingredient_name}
                      qty={formatQuantity(ingredient.amount, ingredient.unit)}
                    />
                  )),
                )}
              </div>
            </div>

            <div className={styles.section}>
              <div className={styles.sectionLabel}>Method</div>
              <div className={styles.methodGroups}>
                {shownElements.map((element) => (
                  <div key={element.name} className={styles.methodGroup}>
                    {showComponentHeadings && (
                      <div className={styles.componentHeading}>
                        {element.role && (
                          <span className={styles.componentHeadingRole}>{element.role}</span>
                        )}
                        <span className={styles.componentHeadingName}>{element.name}</span>
                      </div>
                    )}
                    <div className={styles.stepsList}>
                      {element.steps.map((step) => (
                        <MethodStep
                          key={`${element.name}-${step.step_number}`}
                          number={step.step_number}
                          text={step.instruction}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {awaitingRecipe && (
        <div className={styles.footer}>
          <PillButton variant="footer" onClick={handleReverseEngineer} disabled={isStartingRecipe}>
            {isStartingRecipe ? 'Starting…' : 'Reverse engineer this dish'}
          </PillButton>
        </div>
      )}
    </div>
  );
}
