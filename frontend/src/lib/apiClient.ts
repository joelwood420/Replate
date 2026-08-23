const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:7071/api';

export type AuthHeaders = Record<string, string>;

/**
 * Mirrors shared/models.py's JobStatus. The pipeline runs in two stages:
 * `Identified` means stage 1 finished - the dish is in the cookbook with a matched
 * restaurant and menu item, but no recipe yet. `Generating` means the user pressed
 * "Reverse engineer" and stage 2 is running. `Failed` only ever means stage 1 failed;
 * a stage-2 failure reverts to `Identified` with an error_message so it stays retryable.
 */
export type JobStatusValue =
  | 'Queued'
  | 'Processing'
  | 'Identified'
  | 'Generating'
  | 'Completed'
  | 'Failed';
export type MatchMethod = 'menu_matched' | 'vision_only_medium' | 'vision_only_low';

export interface CreateJobResponse {
  job_id: string;
  upload_url: string;
  /** S3 object key the job was created against. Returned for traceability; not sent back. */
  image_key: string;
}

export interface RestaurantCandidate {
  place_id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
}

export type SelectedRestaurant = RestaurantCandidate;

export type CreateJobInput =
  | { latitude: number; longitude: number }
  | { selected_restaurant: SelectedRestaurant };

export interface Ingredient {
  ingredient_name: string;
  amount: string | null;
  unit: string | null;
}

export interface RecipeStep {
  step_number: number;
  instruction: string;
}

export interface DishElement {
  name: string;
  description: string | null;
  role: string | null;
  ingredients: Ingredient[];
  steps: RecipeStep[];
}

export interface JobResult {
  dish_name: string | null;
  cuisine: string | null;
  confidence: number | null;
  matched_restaurant_id: string | null;
  restaurant_name: string | null;
  matched_menu_item_id: string | null;
  match_confidence: number | null;
  match_method: MatchMethod;
  elements: DishElement[];
}

export interface JobDetail {
  job_id: string;
  status: JobStatusValue;
  image_url: string;
  is_saved: boolean;
  created_at: string | null;
  error_message?: string;
  result?: JobResult;
}

export interface JobSummary {
  job_id: string;
  status: JobStatusValue;
  is_saved: boolean;
  created_at: string | null;
  dish_name: string | null;
  restaurant_name: string | null;
  image_url: string;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit, authHeaders: AuthHeaders): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...authHeaders, ...(init.headers ?? {}) },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}) as { error?: string });
    throw new ApiError(response.status, body.error ?? `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function createJob(input: CreateJobInput, authHeaders: AuthHeaders): Promise<CreateJobResponse> {
  return request(
    '/jobs',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    authHeaders,
  );
}

export function searchRestaurants(
  params: { query: string; latitude?: number; longitude?: number },
  authHeaders: AuthHeaders,
): Promise<{ restaurants: RestaurantCandidate[] }> {
  const qs = new URLSearchParams({ query: params.query });
  if (params.latitude !== undefined) qs.set('latitude', String(params.latitude));
  if (params.longitude !== undefined) qs.set('longitude', String(params.longitude));
  return request(`/restaurants/search?${qs.toString()}`, { method: 'GET' }, authHeaders);
}

export async function uploadPhotoToBlob(uploadUrl: string, file: Blob): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    headers: {
      'x-ms-blob-type': 'BlockBlob',
      'Content-Type': file.type || 'image/jpeg',
    },
    body: file,
  });

  if (!response.ok) {
    throw new ApiError(response.status, `Photo upload failed with status ${response.status}`);
  }
}

/**
 * Tells the backend the photo has finished uploading, which is what actually starts
 * the pipeline. `createJob` only reserves the upload slot: it cannot enqueue the job
 * itself, because at that point the blob it names does not exist yet and the
 * orchestrator would race the PUT above.
 */
export function markUploadComplete(
  jobId: string,
  authHeaders: AuthHeaders,
): Promise<{ job_id: string; status: JobStatusValue }> {
  return request(`/jobs/${jobId}/uploaded`, { method: 'POST' }, authHeaders);
}

export function getJob(jobId: string, authHeaders: AuthHeaders): Promise<JobDetail> {
  return request(`/jobs/${jobId}`, { method: 'GET' }, authHeaders);
}

/**
 * Starts stage 2 for an already-identified dish. Returns as soon as the orchestration
 * is queued (202) - poll the job to watch it move Generating -> Completed.
 * Throws ApiError 409 if the dish is not in the `Identified` state.
 */
export function reverseEngineerJob(
  jobId: string,
  authHeaders: AuthHeaders,
): Promise<{ job_id: string; status: JobStatusValue }> {
  return request(`/jobs/${jobId}/reverse-engineer`, { method: 'POST' }, authHeaders);
}

export function listJobs(
  options: { saved?: boolean; limit?: number } | undefined,
  authHeaders: AuthHeaders,
): Promise<JobSummary[]> {
  const params = new URLSearchParams();
  if (options?.saved !== undefined) params.set('saved', String(options.saved));
  if (options?.limit !== undefined) params.set('limit', String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/jobs${query}`, { method: 'GET' }, authHeaders);
}

export interface UserProfile {
  display_name: string | null;
  email: string | null;
  created_at: string | null;
}

export function getProfile(authHeaders: AuthHeaders): Promise<UserProfile> {
  return request('/profile', { method: 'GET' }, authHeaders);
}

export function updateProfile(
  displayName: string,
  authHeaders: AuthHeaders,
): Promise<UserProfile> {
  return request(
    '/profile',
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    },
    authHeaders,
  );
}

export function setJobSaved(
  jobId: string,
  saved: boolean,
  authHeaders: AuthHeaders,
): Promise<{ job_id: string; is_saved: boolean }> {
  return request(
    `/jobs/${jobId}/save`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ saved }),
    },
    authHeaders,
  );
}
