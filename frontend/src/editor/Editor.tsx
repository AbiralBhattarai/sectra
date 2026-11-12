import { useEffect, useState } from "react";
import { deleteSelection, redo, splitAtPlayhead, undo } from "./actions";
import { run } from "./commands";
import { loadClip, loadMediaSizes } from "./loadClip";
import { Preview } from "./Preview";
import { SidePanel } from "./SidePanel";
import { useEditor } from "./store";
import type { AspectRatio } from "./types";
import { useClipSync } from "./useClipSync";
import { useFaceTracking } from "./useFaceTracking";
import { useShortcuts } from "./useShortcuts";
import type { Video } from "../api/types";

interface Props {
  clipId: string;
  video: Video;
}

export function Editor({ clipId, video }: Props) {
  const clip = useEditor((s) => s.clip);
  const [error, setError] = useState<string | null>(null);
  useClipSync();
  useShortcuts();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    loadClip(clipId, video)
      .then(({ clip, assets }) => !cancelled && useEditor.getState().open(clip, video, assets))
      .then(() => loadMediaSizes())
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      useEditor.getState().close();
    };
  }, [clipId]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const selection = useEditor((s) => s.selection);
  const canUndo = useEditor((s) => s.canUndo);
  const canRedo = useEditor((s) => s.canRedo);
  const saveState = useEditor((s) => s.saveState);
  const saveError = useEditor((s) => s.saveError);
  const faces = useFaceTracking();

  return (
    <header className="toolbar">
      <h2 className="clip-heading" title={clip.reason}>
        {clip.title}
      </h2>
      <select
        value={edl.aspect}
        onChange={(event) => run({ op: "update_clip", aspect: event.target.value as AspectRatio })}
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
          onChange={(event) => run({ op: "update_clip", split_screen: event.target.checked })}
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
      <button type="button" onClick={deleteSelection} disabled={!selection} title="Delete selection (Delete)">
        Delete
      </button>
      <button type="button" onClick={undo} disabled={!canUndo} title="Undo (⌘Z)">
        Undo
      </button>
      <button type="button" onClick={redo} disabled={!canRedo} title="Redo (⇧⌘Z)">
        Redo
      </button>
      <span className={`save-state ${saveState}`} title={saveError ?? undefined}>
        {saveState === "error" ? (saveError ?? "Edit failed") : SAVE_LABELS[saveState]}
      </span>
    </header>
  );
}

const SAVE_LABELS = { saved: "Saved", saving: "Saving…", error: "Edit failed" };
