import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ComponentCard } from '../components/ComponentCard';
import { ErrorState } from '../components/ErrorState';
import { IngredientRow } from '../components/IngredientRow';
import { MethodStep } from '../components/MethodStep';
import { PillButton } from '../components/PillButton';
import { ProcessingOrb } from '../components/ProcessingOrb';
import { RecipeHero } from '../components/RecipeHero';
import { reverseEngineerJob, setJobSaved } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { formatQuantity, timeAgo } from '../lib/format';
import { useJobPolling } from '../lib/jobs/useJobPolling';
import styles from './JobScreen.module.css';

function ProcessingShell() {
  return (
    <div className={styles.processingScreen}>
      <ProcessingOrb />
    </div>
  );
}

export function JobScreen() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { authHeaders } = useAuth();
  const { job, error, isLoading, refetch } = useJobPolling(jobId);
  const [isSaved, setIsSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isStartingRecipe, setIsStartingRecipe] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  // Which component's recipe to show; null shows the full dish (every component combined).
  const [selectedComponent, setSelectedComponent] = useState<number | null>(null);

  useEffect(() => {
    if (job) setIsSaved(job.is_saved);
  }, [job?.job_id, job?.is_saved]);

  // A different dish means the previous component selection no longer applies.
  useEffect(() => {
    setSelectedComponent(null);
  }, [job?.job_id]);

  async function handleToggleSaved() {
    if (!jobId || isSaving) return;
    const next = !isSaved;
    setIsSaving(true);
    try {
      await setJobSaved(jobId, next, authHeaders);
      setIsSaved(next);
    } finally {
      setIsSaving(false);
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
    return <ErrorState message={error} onRetry={refetch} />;
  }

  if (isLoading || !job) {
    return <ProcessingShell />;
  }

  if (job.status === 'Failed') {
    return <ErrorState message={job.error_message ?? 'This scan failed. Try another photo.'} />;
  }

  // Stage 1 (identifying the dish) and stage 2 (generating the recipe) share the same
  // full-screen loading experience.
  if (job.status === 'Queued' || job.status === 'Processing' || job.status === 'Generating') {
    return <ProcessingShell />;
  }

  const { result } = job;
  if (!result) {
    return <ErrorState message="This dish finished processing but no result was found." />;
  }

  const awaitingRecipe = job.status === 'Identified';
  // Clicking a component filters the ingredients + method below to just that component;
  // clicking it again (selectedComponent back to null) restores the full recipe.
  const shownElements =
    selectedComponent === null ? result.elements : [result.elements[selectedComponent]];
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
          isSaved={isSaved}
          onBack={() => navigate(-1)}
          onToggleSaved={handleToggleSaved}
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
              <div className={styles.stepsList}>
                {shownElements.flatMap((element) =>
                  element.steps.map((step) => (
                    <MethodStep key={`${element.name}-${step.step_number}`} number={step.step_number} text={step.instruction} />
                  )),
                )}
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
