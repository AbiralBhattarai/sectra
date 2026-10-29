export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type JobType =
  | "ping"
  | "ingest"
  | "normalize"
  | "prepare"
  | "vad"
  | "transcribe"
  | "analyze"
  | "export";

/** Mirrors the backend `JobEvent` pushed over /api/events. */
export interface JobEvent {
  job_id: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  error: string | null;
  video_id: string | null;
  clip_id: string | null;
}

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  video_id: string | null;
  progress: number;
  error: string | null;
}

/** An export job plus download links once it succeeded. */
export interface Export extends Job {
  clip_id: string | null;
  created_at: string;
  video_url: string | null;
  subtitles_url: string | null;
}

export type VideoStatus = "processing" | "ready" | "failed";

export interface Video {
  id: string;
  title: string;
  source_url: string | null;
  status: VideoStatus;
  duration: number | null;
  width: number | null;
  height: number | null;
  created_at: string;
  current_job: Job | null;
}

export type VideoFile =
  | "source.mp4"
  | "peaks.json"
  | "thumbnail.jpg"
  | "speech.json"
  | "transcript.json";

export interface Clip {
  id: string;
  video_id: string;
  title: string;
  hook: string;
  score: number;
  reason: string;
  /** Source span in seconds. */
  start: number;
  end: number;
  created_at: string;
  updated_at: string;
}
