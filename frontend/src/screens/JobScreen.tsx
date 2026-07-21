import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ComponentCard } from '../components/ComponentCard';
import { ErrorState } from '../components/ErrorState';
import { IngredientRow } from '../components/IngredientRow';
import { MethodStep } from '../components/MethodStep';
import { PillButton } from '../components/PillButton';
import { ProcessingOrb } from '../components/ProcessingOrb';
import { RecipeHero } from '../components/RecipeHero';
import { setJobSaved } from '../lib/apiClient';
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
  const { job, error, isLoading } = useJobPolling(jobId);
  const [isSaved, setIsSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (job) setIsSaved(job.is_saved);
  }, [job?.job_id, job?.is_saved]);

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

  if (error) {
    return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  }

  if (isLoading || !job) {
    return <ProcessingShell />;
  }

  if (job.status === 'Failed') {
    return <ErrorState message={job.error_message ?? 'This scan failed. Try another photo.'} />;
  }

  if (job.status === 'Queued' || job.status === 'Processing') {
    return <ProcessingShell />;
  }

  const { result } = job;
  if (!result) {
    return <ErrorState message="This dish finished processing but no result was found." />;
  }

  const mode: 'new' | 'cookbook' = isSaved ? 'cookbook' : 'new';
  const restaurantMeta = `${result.restaurant_name ?? 'Unknown restaurant'} · identified ${timeAgo(job.created_at)}`;

  return (
    <div className={styles.screen}>
      <div className={styles.scrollArea}>
        <RecipeHero
          imageUrl={job.image_url}
          dishName={result.dish_name ?? 'Your dish'}
          restaurantMeta={restaurantMeta}
          matchMethod={result.match_method}
          mode={mode}
          isSaved={isSaved}
          onBack={() => navigate(-1)}
          onToggleSaved={handleToggleSaved}
        />

        <div className={styles.section}>
          <div className={styles.sectionLabel}>The Components</div>
          <div className={styles.componentsGrid}>
            {result.elements.map((element) => (
              <ComponentCard key={element.name} role={element.role} name={element.name} />
            ))}
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>Ingredients</div>
          <div className={styles.ingredientsList}>
            {result.elements.flatMap((element) =>
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
            {result.elements.flatMap((element) =>
              element.steps.map((step) => (
                <MethodStep key={`${element.name}-${step.step_number}`} number={step.step_number} text={step.instruction} />
              )),
            )}
          </div>
        </div>
      </div>

      {mode === 'new' && (
        <div className={styles.footer}>
          <PillButton variant="footer" onClick={handleToggleSaved} disabled={isSaving}>
            + Add to My Cookbook
          </PillButton>
        </div>
      )}
    </div>
  );
}
