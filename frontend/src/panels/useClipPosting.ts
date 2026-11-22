import { useCallback, useEffect, useRef, useState } from "react";
import { getPostStatus, postClip } from "../api/client";
import type { Clip, PostStatus } from "../api/types";

/** Where one clip's Post is: rendering into the outbox, then posting (the host poster,
 * `poster serve`, picks it up), then done per platform. */
export interface PostState {
  phase: "starting" | "rendering" | "posting" | "done" | "failed";
  /** Render progress 0..1 while rendering. */
  progress: number;
  status?: PostStatus;
  error?: string;
}

const POLL_MS = 4000;

/** A platform is finished when it posted, gave up after repeated failures, or is
 * blocked (logged out / captcha: needs `poster login`). */
export function platformState(status: PostStatus, platform: string): "posted" | "failed" | "blocked" | "pending" {
  if (status.posted[platform]) return "posted";
  if (status.failures[platform]?.gave_up) return "failed";
  if (status.blocked[platform]) return "blocked";
  return "pending";
}

function toState(status: PostStatus): PostState {
  const job = status.export;
  if (job.status === "failed") return { phase: "failed", progress: 0, status, error: job.error ?? "Render failed" };
  if (job.status !== "succeeded") return { phase: "rendering", progress: job.progress, status };
  if (!status.in_outbox) return { phase: "posting", progress: 1, status };
  const finished = status.platforms.every((p) => platformState(status, p) !== "pending");
  return { phase: finished ? "done" : "posting", progress: 1, status };
}

/** One-click Post per clip. Polls while a Post is in flight (it's a render job, then
 * file updates by the host poster, which sends no events). */
export function useClipPosting(clips: Clip[]) {
  const [states, setStates] = useState<Record<string, PostState>>({});
  const active = useRef(new Set<string>());
  const clipIds = clips.map((c) => c.id).join(",");

  const set = (clipId: string, state: PostState) => setStates((current) => ({ ...current, [clipId]: state }));

  // Show earlier Posts of these clips (and resume watching unfinished ones).
  useEffect(() => {
    let cancelled = false;
    for (const id of clipIds.split(",").filter(Boolean)) {
      getPostStatus(id)
        .then((status) => {
          if (cancelled || !status) return;
          const state = toState(status);
          set(id, state);
          if (state.phase === "rendering" || state.phase === "posting") active.current.add(id);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [clipIds]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      for (const id of [...active.current]) {
        getPostStatus(id)
          .then((status) => {
            if (!status) return;
            const state = toState(status);
            set(id, state);
            if (state.phase === "done" || state.phase === "failed") active.current.delete(id);
          })
          .catch(() => undefined);
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const post = useCallback(async (clip: Clip, postCaption: string) => {
    set(clip.id, { phase: "starting", progress: 0 });
    try {
      const status = await postClip(clip.id, postCaption);
      set(clip.id, toState(status));
      active.current.add(clip.id);
    } catch (e) {
      set(clip.id, { phase: "failed", progress: 0, error: (e as Error).message });
    }
  }, []);

  return { states, post };
}
