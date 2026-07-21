const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:7071/api';

export type AuthHeaders = Record<string, string>;

export type JobStatusValue = 'Queued' | 'Processing' | 'Completed' | 'Failed';
export type MatchMethod = 'menu_matched' | 'vision_only_medium' | 'vision_only_low';

export interface CreateJobResponse {
  job_id: string;
  upload_url: string;
  blob_url: string;
}

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

export function createJob(
  input: { latitude: number; longitude: number },
  authHeaders: AuthHeaders,
): Promise<CreateJobResponse> {
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

export function getJob(jobId: string, authHeaders: AuthHeaders): Promise<JobDetail> {
  return request(`/jobs/${jobId}`, { method: 'GET' }, authHeaders);
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
