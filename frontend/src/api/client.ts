import type { ClipDetail, EditCommand, ImageAsset, MusicTrack } from "../editor/types";
import type { Clip, Export, Job, Video, VideoFile, VideoKind } from "./types";

/** An API error; `status` lets callers tell a conflict (409) from a rejected edit (422). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(describeError(body) ?? `${response.status} ${response.statusText}`, response.status);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function describeError(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return null;
}

export const listVideos = (kind?: VideoKind) =>
  request<Video[]>(kind ? `/api/videos?kind=${kind}` : "/api/videos");

export const getVideo = (id: string) => request<Video>(`/api/videos/${id}`);

export const addVideoUrl = (url: string, kind: VideoKind = "source") =>
  request<Video>("/api/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, kind }),
  });

export const listClips = (videoId: string) => request<Clip[]>(`/api/videos/${videoId}/clips`);

export const getClip = (id: string) => request<ClipDetail>(`/api/clips/${id}`);

/** Apply edit commands as one revision; 409 when `baseRevision` is stale. */
export const applyEdits = (id: string, commands: EditCommand[], baseRevision: number) =>
  request<ClipDetail>(`/api/clips/${id}/edits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commands, base_revision: baseRevision }),
  });

export const undoClip = (id: string) => request<ClipDetail>(`/api/clips/${id}/undo`, { method: "POST" });

export const redoClip = (id: string) => request<ClipDetail>(`/api/clips/${id}/redo`, { method: "POST" });

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
  kind: VideoKind = "source",
): Promise<Video> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/videos/upload?filename=${encodeURIComponent(file.name)}&kind=${kind}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || "null");
      if (xhr.status < 300) resolve(body as Video);
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

export const listImages = () => request<ImageAsset[]>("/api/images");

export const imageUrl = (file: string) => `/api/images/${encodeURIComponent(file)}`;

export const uploadImage = (file: File) =>
  request<ImageAsset>(`/api/images/upload?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
  });

export const listExports = (clipId: string) => request<Export[]>(`/api/clips/${clipId}/exports`);

export const requestExport = (clipId: string) =>
  request<Export>(`/api/clips/${clipId}/exports`, { method: "POST" });

/** A face-tracking job covering the clip's video (an existing one when it can); the
 * worker applies the result to the clip itself. */
export const requestTracking = (clipId: string) =>
  request<Job>(`/api/clips/${clipId}/tracking`, { method: "POST" });

export const findClipsAgain = (videoId: string) =>
  request<unknown>(`/api/videos/${videoId}/analyze`, { method: "POST" });
