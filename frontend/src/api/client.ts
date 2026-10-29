import type { ClipDetail, Edl, MusicTrack } from "../editor/types";
import type { Clip, Export, Video, VideoFile } from "./types";

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

export const addVideoUrl = (url: string) =>
  request<Video>("/api/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

export const listClips = (videoId: string) => request<Clip[]>(`/api/videos/${videoId}/clips`);

export const getClip = (id: string) => request<ClipDetail>(`/api/clips/${id}`);

export const updateClip = (id: string, edl: Edl) =>
  request<ClipDetail>(`/api/clips/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edl }),
  });

export const getMediaJson = <T>(videoId: string, file: VideoFile) => request<T>(mediaUrl(videoId, file));

export const deleteVideo = (id: string) =>
  request<void>(`/api/videos/${id}`, { method: "DELETE" });

export const retryJob = (jobId: string) =>
  request<unknown>(`/api/jobs/${jobId}/retry`, { method: "POST" });

export const mediaUrl = (videoId: string, file: VideoFile) =>
  `/api/videos/${videoId}/media/${file}`;

/** Streams the file as the raw request body. XHR because fetch can't report upload progress. */
export function uploadVideo(file: File, onProgress: (fraction: number) => void): Promise<Video> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/videos/upload?filename=${encodeURIComponent(file.name)}`);
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

export const listExports = (clipId: string) => request<Export[]>(`/api/clips/${clipId}/exports`);

export const requestExport = (clipId: string) =>
  request<Export>(`/api/clips/${clipId}/exports`, { method: "POST" });

export const findClipsAgain = (videoId: string) =>
  request<unknown>(`/api/videos/${videoId}/analyze`, { method: "POST" });
