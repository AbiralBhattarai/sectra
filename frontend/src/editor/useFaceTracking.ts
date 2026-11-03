import { useCallback, useEffect, useRef, useState } from "react";
import { getTracking, requestTracking } from "../api/client";
import { useJobEvents } from "../api/useJobEvents";
import { mergeTracking, tracksRanges } from "./edlOps";
import { useEditor } from "./store";
import type { Edl } from "./types";

export interface TrackingState {
  status: "tracking" | "failed";
  progress: number;
  error?: string;
}

/** The "Face tracking" checkbox. Ticking it reuses shots that cover the clip, or runs a
 * TRACK job and applies the result as one edit (the worker never writes the EDL, so
 * autosave can't overwrite it). Trimming past the tracked span tracks the rest. */
export function useFaceTracking() {
  const clipId = useEditor((s) => s.clip?.id);
  const tracking = useEditor((s) => s.edl?.tracking ?? null);
  const ranges = useEditor((s) => s.edl?.ranges);
  const [state, setState] = useState<TrackingState | null>(null);
  // The job this editor waits on, and the clip it is for.
  const waiting = useRef<{ jobId: string; clipId: string } | null>(null);

  const apply = useCallback(async (jobId: string, forClip: string) => {
    const result = await getTracking(jobId);
    const { clip, edit } = useEditor.getState();
    if (clip?.id !== forClip) return;
    edit((e) => ({ ...e, split_screen: false, tracking: mergeTracking(e.tracking, result) }));
    setState(null);
  }, []);

  const fail = (error: string) => setState({ status: "failed", progress: 0, error });

  const start = useCallback(async () => {
    const forClip = useEditor.getState().clip!.id;
    setState({ status: "tracking", progress: 0 });
    try {
      const job = await requestTracking(forClip);
      if (job.status === "succeeded") await apply(job.id, forClip);
      else waiting.current = { jobId: job.id, clipId: forClip };
    } catch (e) {
      fail((e as Error).message);
    }
  }, [apply]);

  useJobEvents((event) => {
    const job = waiting.current;
    if (!job || event.job_id !== job.jobId) return;
    if (event.status === "succeeded") {
      waiting.current = null;
      apply(job.jobId, job.clipId).catch((e: Error) => fail(e.message));
    } else if (event.status === "failed") {
      waiting.current = null;
      fail(event.error ?? "Face tracking failed");
    } else {
      setState({ status: "tracking", progress: event.progress });
    }
  });

  useEffect(() => {
    waiting.current = null;
    setState(null);
  }, [clipId]);

  // Trimmed past what was tracked: track the new stretch too.
  const uncovered = tracking?.enabled === true && ranges != null && !tracksRanges(tracking, ranges);
  useEffect(() => {
    if (uncovered && !waiting.current) void start();
  }, [uncovered, start]);

  /** Forget a running job (its result won't be applied). */
  const stop = () => {
    waiting.current = null;
    setState(null);
  };

  const toggle = (on: boolean) => {
    const { edl, edit } = useEditor.getState();
    if (!on) {
      stop();
      edit(withoutTracking);
    } else if (edl!.tracking && tracksRanges(edl!.tracking, edl!.ranges)) {
      edit((e) => ({ ...e, split_screen: false, tracking: { ...e.tracking!, enabled: true } }));
    } else {
      void start();
    }
  };

  return { checked: tracking?.enabled === true || state?.status === "tracking", state, toggle, stop };
}

export const withoutTracking = (e: Edl): Edl =>
  e.tracking ? { ...e, tracking: { ...e.tracking, enabled: false } } : e;
