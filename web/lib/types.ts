/** Types mirroring FastAPI response shapes (stories A2/A3/B1/E1). */

export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "CANCELLING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";

export interface JobSpec {
  image: string;
  command: string[];
  env: Record<string, string>;
  gpu: boolean;
  timeout_minutes: number;
}

export interface Job {
  id: string;
  name: string;
  spec: JobSpec;
  status: JobStatus;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  worker_id: string | null;
  exit_code: number | null;
  error_message: string | null;
}

export interface JobList {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface SubmitJobPayload {
  name: string;
  spec: JobSpec;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
  must_change_password: boolean;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  rate_limit_tier: string;
  expires_at: string | null;
  revoked: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  store_this_now: string;
}

export interface CreateApiKeyPayload {
  name: string;
  scopes: string[];
  expires_at?: string | null;
}

export interface QuotaUsageEntry {
  limit: number;
  current: number;
}

export interface MeQuota {
  limits: {
    max_concurrent_jobs: number;
    max_jobs_per_day: number;
    max_storage_mb: number;
    max_instances: number;
    max_llm_tokens_per_day: number;
  };
  usage: Record<string, QuotaUsageEntry>;
}

export const ALLOWED_IMAGES = [
  "python:3.12-alpine",
  "python:3.12-slim",
  "pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime",
  "tensorflow/tensorflow:2.16.1",
  "nvidia/cuda:12.4.1-runtime-ubuntu22.04",
] as const;

export const API_KEY_SCOPES = [
  "jobs:read",
  "jobs:write",
  "models:read",
  "llm:invoke",
  "instances:manage",
] as const;

export const PASSWORD_CHANGE_REQUIRED = "password change required";
