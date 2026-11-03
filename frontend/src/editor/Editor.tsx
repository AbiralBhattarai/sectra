import { useEffect, useState } from "react";
import { useStore } from "zustand";
import type { Video } from "../api/types";
import { deleteRange, splitAt } from "./edlOps";
import { loadClip } from "./loadClip";
import { Preview } from "./Preview";
import { SidePanel } from "./SidePanel";
import { redo, undo, useEditor } from "./store";
import type { AspectRatio } from "./types";
import { useAutosave } from "./useAutosave";
import { useFaceTracking, withoutTracking } from "./useFaceTracking";

interface Props {
  clipId: string;
  video: Video;
}

export function Editor({ clipId, video }: Props) {
  const clip = useEditor((s) => s.clip);
  const [error, setError] = useState<string | null>(null);
  useAutosave();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    loadClip(clipId, video)
      .then(({ clip, assets }) => !cancelled && useEditor.getState().open(clip, video, assets))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      useEditor.getState().close();
    };
  }, [clipId]); // eslint-disable-line react-hooks/exhaustive-deps

  useShortcuts();

  if (error) return <p className="error">Could not open clip: {error}</p>;
  if (!clip || clip.id !== clipId) return <p className="placeholder">Loading clip…</p>;
  return (
    <>
      <Toolbar />
      <div className="editor-body">
        <Preview />
        <SidePanel />
      </div>
    </>
  );
}

function Toolbar() {
  const clip = useEditor((s) => s.clip)!;
  const edl = useEditor((s) => s.edl)!;
  const selectedRange = useEditor((s) => s.selectedRange);
  const saveState = useEditor((s) => s.saveState);
  const saveError = useEditor((s) => s.saveError);
  const canUndo = useStore(useEditor.temporal, (s) => s.pastStates.length > 0);
  const canRedo = useStore(useEditor.temporal, (s) => s.futureStates.length > 0);
  const { edit } = useEditor.getState();
  const faces = useFaceTracking();

  return (
    <header className="toolbar">
      <h2 className="clip-heading" title={clip.reason}>
        {clip.title}
      </h2>
      <select
        value={edl.aspect}
        onChange={(event) => edit((e) => ({ ...e, aspect: event.target.value as AspectRatio }))}
        aria-label="Aspect ratio"
      >
        <option value="9:16">9:16</option>
        <option value="1:1">1:1</option>
        <option value="16:9">16:9</option>
      </select>
      <label className="checkbox" title="Stack the left half of the video over the right half">
        <input
          type="checkbox"
          checked={edl.split_screen && !faces.checked}
          onChange={(event) => {
            const on = event.target.checked;
            if (on) faces.stop();
            edit((e) => ({ ...(on ? withoutTracking(e) : e), split_screen: on }));
          }}
        />
        OmeTV split
      </label>
      <label
        className="checkbox"
        title={faces.state?.error ?? "Cut to whoever is speaking (drag the preview to reframe a shot)"}
      >
        <input type="checkbox" checked={faces.checked} onChange={(event) => faces.toggle(event.target.checked)} />
        Face tracking
        {faces.state?.status === "tracking" && ` ${Math.round(faces.state.progress * 100)}%`}
        {faces.state?.status === "failed" && <span className="error"> failed</span>}
      </label>
      <button type="button" onClick={splitAtPlayhead} title="Split at playhead (S)">
        Split
      </button>
      <button
        type="button"
        onClick={deleteSelected}
        disabled={selectedRange == null || edl.ranges.length < 2}
        title="Delete selected range (Delete)"
      >
        Delete
      </button>
      <button type="button" onClick={undo} disabled={!canUndo} title="Undo (⌘Z)">
        Undo
      </button>
      <button type="button" onClick={redo} disabled={!canRedo} title="Redo (⇧⌘Z)">
        Redo
      </button>
      <span className={`save-state ${saveState}`} title={saveError ?? undefined}>
        {SAVE_LABELS[saveState]}
      </span>
    </header>
  );
}

const SAVE_LABELS = { saved: "Saved", pending: "Unsaved", saving: "Saving…", error: "Save failed" };

function splitAtPlayhead() {
  const { edit, playhead } = useEditor.getState();
  edit((e) => splitAt(e, playhead));
}

function deleteSelected() {
  const { edit, selectedRange, selectRange } = useEditor.getState();
  if (selectedRange == null) return;
  edit((e) => deleteRange(e, selectedRange));
  selectRange(null);
}

function useShortcuts() {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable=true]")) return;
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      } else if (mod && event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
      } else if (event.key === " ") {
        event.preventDefault();
        useEditor.getState().togglePlay();
      } else if (event.key.toLowerCase() === "s" && !mod) {
        splitAtPlayhead();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        deleteSelected();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
