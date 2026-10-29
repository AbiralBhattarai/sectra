import { useEffect } from "react";
import { updateClip } from "../api/client";
import type { Edl } from "./types";
import { useEditor } from "./store";

const DEBOUNCE_MS = 800;

/** Saves the edit shortly after it stops changing. Saves run one at a time; a change
 * made while one is in flight is saved right after it. Switching clips flushes. */
export function useAutosave(): void {
  useEffect(() => {
    let pending: { clipId: string; edl: Edl } | null = null;
    let timer: number | undefined;
    let saving = false;

    const flush = async () => {
      window.clearTimeout(timer);
      if (saving || !pending) return;
      const { clipId, edl } = pending;
      pending = null;
      saving = true;
      const isCurrent = () => useEditor.getState().clip?.id === clipId;
      if (isCurrent()) useEditor.getState().setSaveState("saving");
      try {
        const saved = await updateClip(clipId, edl);
        if (isCurrent() && !pending) useEditor.getState().setSaved(saved);
      } catch (e) {
        if (isCurrent()) useEditor.getState().setSaveState("error", (e as Error).message);
      } finally {
        saving = false;
        if (pending) void flush();
      }
    };

    const unsubscribe = useEditor.subscribe((state, previous) => {
      if (previous.clip && previous.clip.id !== state.clip?.id) {
        void flush(); // leaving a clip: don't wait for the debounce
        return;
      }
      if (!state.clip || !state.edl || state.edl === previous.edl) return;
      pending = { clipId: state.clip.id, edl: state.edl };
      state.setSaveState("pending");
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void flush(), DEBOUNCE_MS);
    });

    const warn = (event: BeforeUnloadEvent) => {
      if (pending || saving) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      unsubscribe();
      window.removeEventListener("beforeunload", warn);
      void flush();
    };
  }, []);
}
