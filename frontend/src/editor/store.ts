import { create } from "zustand";
import type { Video } from "../api/types";
import { outputDuration } from "./sequence";
import type { ClipDetail, Edl, Peaks, Span, Word } from "./types";

export type SaveState = "saved" | "saving" | "error";

export interface EditorAssets {
  transcript: Word[];
  speech: Span[];
  peaks: Peaks | null;
}

/** What the inspector shows and keyboard shortcuts act on. */
export type Selection =
  | { kind: "segments"; ids: string[] }
  | { kind: "transition"; segmentId: string }
  | { kind: "overlay"; id: string }
  | { kind: "broll"; id: string }
  | null;

export interface MediaSize {
  width: number;
  height: number;
}

interface EditorState extends EditorAssets {
  clip: ClipDetail | null;
  video: Video | null;
  /** The server's copy of the edit; every change goes through a command (commands.ts). */
  edl: Edl | null;
  revision: number;
  canUndo: boolean;
  canRedo: boolean;
  /** Output time (seconds into the clip) of the preview. */
  playhead: number;
  playing: boolean;
  selection: Selection;
  selectedWord: number | null;
  saveState: SaveState;
  saveError: string | null;
  snapping: boolean;
  /** Pixel sizes of the media the clip uses (videos by id, images by file), for framing. */
  mediaSizes: Record<string, MediaSize>;

  open: (clip: ClipDetail, video: Video, assets: EditorAssets) => void;
  close: () => void;
  /** A clip as the server returned it (after an edit, undo/redo or reload). */
  setClip: (clip: ClipDetail) => void;
  setPlayhead: (t: number) => void;
  seek: (t: number) => void;
  setPlaying: (playing: boolean) => void;
  togglePlay: () => void;
  select: (selection: Selection) => void;
  selectWord: (index: number | null) => void;
  setSaveState: (state: SaveState, error?: string) => void;
  setSnapping: (on: boolean) => void;
  noteMediaSize: (key: string, size: MediaSize) => void;
}

const EMPTY = {
  clip: null,
  video: null,
  edl: null,
  revision: 0,
  canUndo: false,
  canRedo: false,
  transcript: [],
  speech: [],
  peaks: null,
  playhead: 0,
  playing: false,
  selection: null,
  selectedWord: null,
} satisfies Partial<EditorState>;

export const useEditor = create<EditorState>()((set, get) => ({
  ...EMPTY,
  saveState: "saved",
  saveError: null,
  snapping: true,
  mediaSizes: {},

  open: (clip, video, assets) => {
    set({
      ...EMPTY,
      ...assets,
      ...fromClip(clip),
      video,
      saveState: "saved",
      saveError: null,
      mediaSizes: { ...get().mediaSizes, [video.id]: { width: video.width ?? 1920, height: video.height ?? 1080 } },
    });
  },
  close: () => set({ ...EMPTY }),
  setClip: (clip) =>
    set((state) => {
      const next = fromClip(clip);
      const duration = outputDuration(next.edl.segments);
      return {
        ...next,
        selection: keepSelection(state.selection, next.edl),
        selectedWord:
          state.selectedWord != null && state.selectedWord < next.edl.captions.words.length ? state.selectedWord : null,
        playhead: Math.min(state.playhead, duration),
      };
    }),
  setPlayhead: (t) => {
    if (t !== get().playhead) set({ playhead: t });
  },
  seek: (t) => {
    const { edl } = get();
    const duration = edl ? outputDuration(edl.segments) : 0;
    set({ playhead: Math.min(Math.max(t, 0), duration) });
  },
  setPlaying: (playing) => set({ playing }),
  togglePlay: () => {
    const { playing, playhead, edl } = get();
    if (!edl) return;
    // From the end, start over.
    if (!playing && playhead >= outputDuration(edl.segments) - 0.01) set({ playhead: 0 });
    set({ playing: !playing });
  },
  select: (selection) => set({ selection }),
  selectWord: (index) => set({ selectedWord: index }),
  setSaveState: (saveState, error) => set({ saveState, saveError: error ?? null }),
  setSnapping: (snapping) => set({ snapping }),
  noteMediaSize: (key, size) => {
    const known = get().mediaSizes[key];
    if (!known || known.width !== size.width || known.height !== size.height) {
      set({ mediaSizes: { ...get().mediaSizes, [key]: size } });
    }
  },
}));

function fromClip(clip: ClipDetail) {
  return { clip, edl: clip.edl, revision: clip.revision, canUndo: clip.can_undo, canRedo: clip.can_redo };
}

/** Drop selected items an edit removed. */
function keepSelection(selection: Selection, edl: Edl): Selection {
  if (!selection) return null;
  const segments = new Set(edl.segments.map((s) => s.id));
  switch (selection.kind) {
    case "segments": {
      const ids = selection.ids.filter((id) => segments.has(id));
      return ids.length ? { kind: "segments", ids } : null;
    }
    case "transition": {
      const segment = edl.segments.find((s) => s.id === selection.segmentId);
      return segment?.transition ? selection : null;
    }
    case "overlay":
      return edl.overlays.some((o) => o.id === selection.id) ? selection : null;
    case "broll":
      return edl.broll.some((b) => b.id === selection.id) ? selection : null;
  }
}

/** Ids of the selected segments (empty unless segments are selected). */
export function selectedSegments(selection: Selection): string[] {
  return selection?.kind === "segments" ? selection.ids : [];
}
