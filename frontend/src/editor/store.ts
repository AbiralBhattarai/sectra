import { temporal } from "zundo";
import { create } from "zustand";
import type { Video } from "../api/types";
import { nextPlayable } from "./edlOps";
import type { ClipDetail, Edl, Peaks, Span, Word } from "./types";

export type SaveState = "saved" | "pending" | "saving" | "error";

export interface EditorAssets {
  transcript: Word[];
  speech: Span[];
  peaks: Peaks | null;
}

interface EditorState extends EditorAssets {
  clip: ClipDetail | null;
  video: Video | null;
  /** The edit being worked on; the only state undo/redo tracks. */
  edl: Edl | null;
  /** Source time of the preview. */
  playhead: number;
  playing: boolean;
  selectedRange: number | null;
  selectedWord: number | null;
  selectedOverlay: number | null;
  saveState: SaveState;
  saveError: string | null;
  media: HTMLVideoElement | null;

  open: (clip: ClipDetail, video: Video, assets: EditorAssets) => void;
  close: () => void;
  /** Every change to the edit goes through here, so each call is one undo step. */
  edit: (change: (edl: Edl) => Edl) => void;
  setMedia: (media: HTMLVideoElement | null) => void;
  setPlayhead: (t: number, playing: boolean) => void;
  seek: (t: number) => void;
  togglePlay: () => void;
  selectRange: (index: number | null) => void;
  selectWord: (index: number | null) => void;
  selectOverlay: (index: number | null) => void;
  setSaved: (clip: ClipDetail) => void;
  setSaveState: (state: SaveState, error?: string) => void;
}

const EMPTY: Pick<
  EditorState,
  | "clip"
  | "video"
  | "edl"
  | "transcript"
  | "speech"
  | "peaks"
  | "playhead"
  | "playing"
  | "selectedRange"
  | "selectedWord"
  | "selectedOverlay"
> = {
  clip: null,
  video: null,
  edl: null,
  transcript: [],
  speech: [],
  peaks: null,
  playhead: 0,
  playing: false,
  selectedRange: null,
  selectedWord: null,
  selectedOverlay: null,
};

export const useEditor = create<EditorState>()(
  temporal(
    (set, get) => ({
      ...EMPTY,
      saveState: "saved",
      saveError: null,
      media: null,

      open: (clip, video, assets) => {
        set({ ...EMPTY, ...assets, clip, video, edl: clip.edl, playhead: clip.edl.ranges[0].start, saveState: "saved", saveError: null });
        useEditor.temporal.getState().clear();
      },
      close: () => {
        set({ ...EMPTY });
        useEditor.temporal.getState().clear();
      },
      edit: (change) => {
        const { edl } = get();
        if (!edl) return;
        const next = change(edl);
        if (next === edl) return;
        const words = next.captions.words.length;
        set((state) => ({
          edl: next,
          selectedRange: state.selectedRange != null && state.selectedRange < next.ranges.length ? state.selectedRange : null,
          selectedWord: state.selectedWord != null && state.selectedWord < words ? state.selectedWord : null,
          selectedOverlay:
            state.selectedOverlay != null && state.selectedOverlay < next.overlays.length ? state.selectedOverlay : null,
        }));
      },
      setMedia: (media) => set({ media }),
      setPlayhead: (t, playing) => {
        if (t !== get().playhead || playing !== get().playing) set({ playhead: t, playing });
      },
      seek: (t) => {
        const { media } = get();
        if (media) media.currentTime = t;
        set({ playhead: t });
      },
      togglePlay: () => {
        const { media, edl } = get();
        if (!media || !edl) return;
        if (!media.paused) {
          media.pause();
          return;
        }
        // From the end (or outside the kept ranges), start over at the first range.
        const at = nextPlayable(media.currentTime, edl.ranges);
        media.currentTime = at ?? edl.ranges[0].start;
        void media.play();
      },
      selectRange: (index) => set({ selectedRange: index }),
      selectWord: (index) => set({ selectedWord: index }),
      selectOverlay: (index) => set({ selectedOverlay: index }),
      setSaved: (clip) => set({ clip, saveState: "saved", saveError: null }),
      setSaveState: (saveState, error) => set({ saveState, saveError: error ?? null }),
    }),
    {
      partialize: (state) => ({ edl: state.edl }),
      equality: (a, b) => a.edl === b.edl,
      limit: 200,
    },
  ),
);

export const undo = () => useEditor.temporal.getState().undo();
export const redo = () => useEditor.temporal.getState().redo();
