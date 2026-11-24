import type { ClipDetail, Edl, MusicTrack, Span, Tracking, Zoom } from "../editor/types";
import type {
  BackgroundLibrary,
  Clip,
  Export,
  Job,
  NewStory,
  PostStatus,
  StoryOptions,
  Video,
  VideoFile,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(describeError(body) ?? `${response.status} ${response.statusText}`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function describeError(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return null;
}

export const listVideos = () => request<Video[]>("/api/videos");

export const getVideo = (id: string) => request<Video>(`/api/videos/${id}`);

export const addVideoUrl = (url: string, clipPrompt = "") =>
  request<Video>("/api/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, clip_prompt: clipPrompt }),
  });

export const listClips = (videoId: string) => request<Clip[]>(`/api/videos/${videoId}/clips`);

export const getClip = (id: string) => request<ClipDetail>(`/api/clips/${id}`);

/** Saves the edit; `caption` is left unchanged when omitted. */
export const updateClip = (id: string, edl: Edl, caption?: string) =>
  request<ClipDetail>(`/api/clips/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(caption === undefined ? { edl } : { edl, caption }),
  });

/** Generated zoom-ins for the clip cut to `ranges` (not saved). */
export const autoZoom = (clipId: string, ranges: Span[]) =>
  request<Zoom[]>(`/api/clips/${clipId}/auto-zoom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ranges }),
  });

export const getMediaJson = <T>(videoId: string, file: VideoFile) => request<T>(mediaUrl(videoId, file));

export const deleteVideo = (id: string) =>
  request<void>(`/api/videos/${id}`, { method: "DELETE" });

export const retryJob = (jobId: string) =>
  request<unknown>(`/api/jobs/${jobId}/retry`, { method: "POST" });

export const mediaUrl = (videoId: string, file: VideoFile) =>
  `/api/videos/${videoId}/media/${file}`;

/** Streams the file as the raw request body. XHR because fetch can't report upload progress. */
export function uploadVideo(
  file: File,
  onProgress: (fraction: number) => void,
  clipPrompt = "",
): Promise<Video> {
  const query = new URLSearchParams({ filename: file.name, clip_prompt: clipPrompt });
  return uploadRaw<Video>(`/api/videos/upload?${query}`, file, onProgress);
}

function uploadRaw<T>(url: string, file: File, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || "null");
      if (xhr.status < 300) resolve(body as T);
      else reject(new Error(describeError(body) ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.send(file);
  });
}

export const listMusic = () => request<MusicTrack[]>("/api/music");

export const musicUrl = (file: string) => `/api/music/${encodeURIComponent(file)}`;

export const uploadMusic = (file: File) =>
  request<MusicTrack>(`/api/music/upload?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
  });

export const listExports = (clipId: string) => request<Export[]>(`/api/clips/${clipId}/exports`);

export const requestExport = (clipId: string) =>
  request<Export>(`/api/clips/${clipId}/exports`, { method: "POST" });

/** Render the clip into the outbox and have the host poster post it everywhere, with the
 * title followed by `postCaption` (saved on the clip) as the description. */
export const postClip = (clipId: string, postCaption: string) =>
  request<PostStatus>(`/api/clips/${clipId}/post`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_caption: postCaption }),
  });

/** The clip's latest Post, or undefined if it was never posted. */
export const getPostStatus = (clipId: string) => request<PostStatus | undefined>(`/api/clips/${clipId}/post`);

/** A face-tracking job covering the clip's ranges (an existing one when it can). */
export const requestTracking = (clipId: string) =>
  request<Job>(`/api/clips/${clipId}/tracking`, { method: "POST" });

export const getTracking = (jobId: string) => request<Tracking>(`/api/tracking/${jobId}`);

/** Re-runs clip finding; `clipPrompt` replaces the stored one ("" = default finder). */
export const findClipsAgain = (videoId: string, clipPrompt?: string) =>
  request<unknown>(`/api/videos/${videoId}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(clipPrompt === undefined ? {} : { clip_prompt: clipPrompt }),
  });

/** Narrator: narrate a story; it shows up in the video list with `kind: "story"`. */
export const createStory = (story: NewStory) =>
  request<Video>("/api/stories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(story),
  });

export const getStoryOptions = () => request<StoryOptions>("/api/stories/options");

/** One SVG layer of a narrator character, e.g. `characterUrl("guy", "mouth/D.svg")`. */
export const characterUrl = (name: string, layer: string) => `/api/characters/${name}/${layer}`;

export const listBackgrounds = () => request<BackgroundLibrary>("/api/backgrounds");

export const addBackgroundUrl = (url: string, category: string) =>
  request<Job>("/api/backgrounds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, category }),
  });

export const uploadBackground = (file: File, category: string, onProgress: (fraction: number) => void) =>
  uploadRaw<Job>(
    `/api/backgrounds/upload?${new URLSearchParams({ filename: file.name, category })}`,
    file,
    onProgress,
  );

export const backgroundUrl = (ref: string) => `/api/backgrounds/${ref}`;

export const deleteBackground = (ref: string) =>
  request<void>(`/api/backgrounds/${ref}`, { method: "DELETE" });
