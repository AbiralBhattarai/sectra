import { useCallback, useEffect, useRef, useState } from "react";
import { requestTracking } from "../api/client";
import { useJobEvents } from "../api/useJobEvents";
import { run } from "./commands";
import { isClipVideo } from "./sequence";
import { useEditor } from "./store";
import type { Edl } from "./types";

export interface TrackingState {
  status: "tracking" | "failed";
  progress: number;
  error?: string;
}

/** The "Face tracking" checkbox. Ticking it reuses shots that cover the clip, or runs a
 * TRACK job; the worker merges the result into the clip itself and the editor picks it
 * up from the clip event. Trimming past the tracked span tracks the rest. */
export function useFaceTracking() {
  const clipId = useEditor((s) => s.clip?.id);
  const edl = useEditor((s) => s.edl);
  const [state, setState] = useState<TrackingState | null>(null);
  const waiting = useRef<string | null>(null);

  const fail = (error: string) => setState({ status: "failed", progress: 0, error });

  const start = useCallback(async () => {
    const forClip = useEditor.getState().clip!.id;
    setState({ status: "tracking", progress: 0 });
    try {
      const job = await requestTracking(forClip);
      if (job.status === "succeeded") {
        // Already tracked: make sure it's switched on.
        setState(null);
        void run({ op: "update_clip", tracking_enabled: true });
      } else {
        waiting.current = job.id;
      }
    } catch (e) {
      fail((e as Error).message);
    }
  }, []);

  useJobEvents((event) => {
    if (event.job_id !== waiting.current) return;
    if (event.status === "succeeded") {
      waiting.current = null;
      setState(null);
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
  const uncovered = edl?.tracking?.enabled === true && !tracksClip(edl);
  useEffect(() => {
    if (uncovered && !waiting.current) void start();
  }, [uncovered, start]);

  const toggle = (on: boolean) => {
    const current = useEditor.getState().edl!;
    if (!on) {
      waiting.current = null;
      setState(null);
      if (current.tracking?.enabled) void run({ op: "update_clip", tracking_enabled: false });
    } else if (current.tracking && tracksClip(current)) {
      void run({ op: "update_clip", tracking_enabled: true });
    } else {
      void start();
    }
  };

  return { checked: edl?.tracking?.enabled === true || state?.status === "tracking", state, toggle };
}

/** Whether face tracking analysed every second of the clip's own video it shows. */
export function tracksClip(edl: Edl): boolean {
  const span = edl.tracking?.span;
  if (!span) return false;
  return edl.segments.every((s) => {
    if (s.kind === "image" || !isClipVideo(s)) return true;
    return s.kind === "video" ? span.start <= s.start && span.end >= s.end : span.start <= s.at && s.at <= span.end;
  });
}
