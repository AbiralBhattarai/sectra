import { maxTransition } from "../timeline/drafts";
import { redo, run, undo } from "./commands";
import { togglePlayback } from "./player/audio";
import { cutTimes, layout, outputDuration, placedAt } from "./sequence";
import { selectedSegments, useEditor } from "./store";
import type { TransitionType } from "./types";

/** Editor actions shared by the toolbar, keyboard shortcuts and context menus. */

export const FRAME = 1 / 30;
const DEFAULT_TRANSITION = 0.5;
let clipboard: string[] = [];

const state = () => useEditor.getState();

export function splitAtPlayhead() {
  return run({ op: "split", at: state().playhead });
}

export function deleteSelection() {
  const { selection, select } = state();
  if (!selection) return;
  select(null);
  switch (selection.kind) {
    case "segments":
      return run({ op: "delete", segment_ids: selection.ids });
    case "transition":
      return run({ op: "remove_transition", segment_id: selection.segmentId });
    case "overlay":
      return run({ op: "remove_overlay", id: selection.id });
    case "broll":
      return run({ op: "remove_broll", id: selection.id });
  }
}

export function duplicateSelection() {
  const ids = selectedSegments(state().selection);
  return run(...ids.map((segment_id) => ({ op: "duplicate" as const, segment_id })));
}

export function copySelection() {
  clipboard = selectedSegments(state().selection);
}

/** Paste copies of the copied segments where the playhead is (before the segment under
 * it, or after it when the playhead is in its second half). */
export function paste() {
  const { edl, playhead } = state();
  if (!edl || !clipboard.length) return;
  const ids = clipboard.filter((id) => edl.segments.some((s) => s.id === id));
  const at = insertionIndex(playhead);
  return run(...ids.map((segment_id, i) => ({ op: "duplicate" as const, segment_id, to_index: at + i })));
}

/** Main-track position for inserting at output time `t`. */
export function insertionIndex(t: number): number {
  const edl = state().edl;
  if (!edl) return 0;
  const p = placedAt(layout(edl.segments), t);
  if (!p) return edl.segments.length;
  return t - p.ownStart < (p.ownEnd - p.ownStart) / 2 ? p.index : p.index + 1;
}

export function freezeAtPlayhead(duration = 1) {
  return run({ op: "freeze_frame", at: state().playhead, duration });
}

export function addMarker() {
  return run({ op: "add_marker", time: state().playhead });
}

/** A transition into `segmentId` (or at the cut nearest the playhead), as long as fits. */
export function addTransition(segmentId?: string, type: TransitionType = "fade") {
  const { edl, playhead, select } = state();
  if (!edl || edl.segments.length < 2) return;
  let index = segmentId ? edl.segments.findIndex((s) => s.id === segmentId) : -1;
  if (index < 1) {
    const cuts = cutTimes(layout(edl.segments));
    const nearest = cuts.reduce((best, t, i) => (Math.abs(t - playhead) < Math.abs(cuts[best] - playhead) ? i : best), 0);
    index = nearest + 1;
  }
  const duration = Math.min(DEFAULT_TRANSITION, Math.floor(maxTransition(edl, index) * 100) / 100);
  if (duration <= 0) return;
  const id = edl.segments[index].id;
  select({ kind: "transition", segmentId: id });
  return run({ op: "set_transition", segment_id: id, type, duration });
}

export function step(seconds: number) {
  const { playhead, seek, setPlaying } = state();
  setPlaying(false);
  seek(playhead + seconds);
}

/** Jump to the previous (-1) or next (+1) cut, or the clip's start/end. */
export function jumpCut(direction: -1 | 1) {
  const { edl, playhead, seek } = state();
  if (!edl) return;
  const times = [0, ...cutTimes(layout(edl.segments)), outputDuration(edl.segments)];
  const target =
    direction > 0 ? times.find((t) => t > playhead + 1e-3) : [...times].reverse().find((t) => t < playhead - 1e-3);
  if (target != null) seek(target);
}

export { redo, togglePlayback, undo };
