import { useEffect } from "react";
import {
  addMarker,
  addTransition,
  copySelection,
  deleteSelection,
  duplicateSelection,
  FRAME,
  jumpCut,
  paste,
  redo,
  splitAtPlayhead,
  step,
  togglePlayback,
  undo,
} from "./actions";
import { useEditor } from "./store";

/** Editor keyboard shortcuts (ignored while typing in a field). */
export const SHORTCUTS: [string, string][] = [
  ["Space / K", "Play / pause"],
  ["J / L", "Back 1 s / play"],
  ["← →", "Step one frame (⇧ = 1 s)"],
  ["↑ ↓", "Previous / next cut"],
  ["S", "Split at playhead"],
  ["Delete", "Delete selection (ripple)"],
  ["⌘D", "Duplicate"],
  ["⌘C / ⌘V", "Copy / paste at playhead"],
  ["T", "Crossfade at nearest cut"],
  ["M", "Add marker"],
  ["N", "Snapping on/off"],
  ["⌘Z / ⇧⌘Z", "Undo / redo"],
  ["Esc", "Clear selection"],
];

export function useShortcuts() {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable=true]")) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      const act = (action: () => unknown) => {
        event.preventDefault();
        void action();
      };
      if (mod) {
        if (key === "z") act(event.shiftKey ? redo : undo);
        else if (key === "y") act(redo);
        else if (key === "d") act(duplicateSelection);
        else if (key === "c") act(copySelection);
        else if (key === "v") act(paste);
        return;
      }
      const editor = useEditor.getState();
      switch (event.key) {
        case " ":
          return act(togglePlayback);
        case "ArrowLeft":
          return act(() => step(event.shiftKey ? -1 : -FRAME));
        case "ArrowRight":
          return act(() => step(event.shiftKey ? 1 : FRAME));
        case "ArrowUp":
          return act(() => jumpCut(-1));
        case "ArrowDown":
          return act(() => jumpCut(1));
        case "Delete":
        case "Backspace":
          return act(deleteSelection);
        case "Escape":
          return act(() => editor.select(null));
      }
      switch (key) {
        case "k":
          return act(() => editor.playing && togglePlayback());
        case "l":
          return act(() => !editor.playing && togglePlayback());
        case "j":
          return act(() => step(-1));
        case "s":
          return act(splitAtPlayhead);
        case "t":
          return act(() => addTransition());
        case "m":
          return act(addMarker);
        case "n":
          return act(() => editor.setSnapping(!editor.snapping));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
