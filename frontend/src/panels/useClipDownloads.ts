import { useCallback, useRef, useState } from "react";
import { listExports, requestExport } from "../api/client";
import type { Clip, Export } from "../api/types";
import { useJobEvents } from "../api/useJobEvents";

export interface DownloadState {
  status: "preparing" | "rendering" | "failed";
  progress: number;
  error?: string;
}

/** One-click download per clip: reuse an export newer than the clip's last edit,
 * otherwise render one and download it the moment it finishes. */
export function useClipDownloads() {
  const [states, setStates] = useState<Record<string, DownloadState>>({});
  // export id → clip id, for renders this panel started and is waiting on.
  const waiting = useRef(new Map<string, string>());

  const set = (clipId: string, state: DownloadState | null) =>
    setStates((current) => {
      const next = { ...current };
      if (state) next[clipId] = state;
      else delete next[clipId];
      return next;
    });

  const finish = useCallback(async (clipId: string, exportId: string) => {
    const done = (await listExports(clipId)).find((e) => e.id === exportId);
    if (done?.video_url) save(done.video_url);
    set(clipId, null);
  }, []);

  useJobEvents((event) => {
    const clipId = waiting.current.get(event.job_id);
    if (!clipId) return;
    if (event.status === "succeeded") {
      waiting.current.delete(event.job_id);
      void finish(clipId, event.job_id);
    } else if (event.status === "failed") {
      waiting.current.delete(event.job_id);
      set(clipId, { status: "failed", progress: 0, error: event.error ?? "Render failed" });
    } else {
      set(clipId, { status: "rendering", progress: event.progress });
    }
  });

  const download = useCallback(async (clip: Clip) => {
    set(clip.id, { status: "preparing", progress: 0 });
    try {
      const reusable = (await listExports(clip.id)).find((e) => isCurrent(e, clip));
      if (reusable?.video_url) {
        save(reusable.video_url);
        set(clip.id, null);
        return;
      }
      const created = await requestExport(clip.id);
      waiting.current.set(created.id, clip.id);
      set(clip.id, { status: "rendering", progress: 0 });
    } catch (e) {
      set(clip.id, { status: "failed", progress: 0, error: (e as Error).message });
    }
  }, []);

  return { states, download };
}

function isCurrent(e: Export, clip: Clip): boolean {
  return e.status === "succeeded" && new Date(e.created_at) >= new Date(clip.updated_at);
}

/** Download via a temporary link; the server sends Content-Disposition: attachment. */
function save(url: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
}
