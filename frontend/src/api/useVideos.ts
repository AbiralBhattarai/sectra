import { useCallback, useEffect, useRef, useState } from "react";
import { getVideo, listVideos } from "./client";
import type { JobEvent, Video } from "./types";
import { useJobEvents } from "./useJobEvents";

/** The video library, kept live: job progress is patched in from SSE events, and a
 * video is refetched when one of its jobs finishes (its title, size or status change). */
export function useVideos() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(videos);
  latest.current = videos;

  const refresh = useCallback(async () => {
    try {
      setVideos(await listVideos());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refetchVideo = useCallback(async (id: string) => {
    try {
      const video = await getVideo(id);
      setVideos((current) => upsert(current, video));
    } catch {
      setVideos((current) => current.filter((v) => v.id !== id)); // deleted meanwhile
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useJobEvents((event: JobEvent) => {
    const videoId = event.video_id;
    if (!videoId) return;
    const known = latest.current.some((video) => video.id === videoId);
    setVideos((current) =>
      current.map((video) =>
        video.id === videoId ? { ...video, current_job: patchJob(event) } : video,
      ),
    );
    if (!known || event.status === "succeeded" || event.status === "failed") {
      void refetchVideo(videoId);
    }
  });

  return {
    videos,
    error,
    upsert: (video: Video) => setVideos((current) => upsert(current, video)),
    remove: (id: string) => setVideos((current) => current.filter((v) => v.id !== id)),
  };
}

function upsert(videos: Video[], video: Video): Video[] {
  return videos.some((v) => v.id === video.id)
    ? videos.map((v) => (v.id === video.id ? video : v))
    : [video, ...videos];
}

function patchJob(event: JobEvent): Video["current_job"] {
  return {
    id: event.job_id,
    type: event.type,
    status: event.status,
    video_id: event.video_id,
    progress: event.progress,
    error: event.error,
  };
}
