import { clamp, layout, MIN_SEGMENT } from "../editor/sequence";
import type { Edl, EditCommand, Segment } from "../editor/types";

/** What dragging on the timeline would do, shown live and sent as one command on release. */

/** A segment with one edge dragged to output time `t` (ripple: later segments follow).
 * Video edges move the in/out point on the source; stills change length. `sourceLength`
 * caps a video's out point (null when unknown). */
export function trimmed(segment: Segment, edge: "start" | "end", t: number, start: number, end: number, sourceLength: number | null): Segment {
  if (segment.kind === "video") {
    if (edge === "start") {
      const from = segment.start + (t - start) * segment.speed;
      return { ...segment, start: clamp(from, 0, segment.end - MIN_SEGMENT * segment.speed) };
    }
    const to = segment.start + (t - start) * segment.speed;
    return { ...segment, end: clamp(to, segment.start + MIN_SEGMENT * segment.speed, sourceLength ?? Infinity) };
  }
  const duration = edge === "end" ? t - start : end - t;
  return { ...segment, duration: clamp(duration, MIN_SEGMENT, 60) };
}

export function trimCommand(segment: Segment): EditCommand {
  return segment.kind === "video"
    ? { op: "trim", segment_id: segment.id, start: round(segment.start), end: round(segment.end) }
    : { op: "trim", segment_id: segment.id, duration: round(segment.duration) };
}

export function withSegment(edl: Edl, segment: Segment): Edl {
  return { ...edl, segments: edl.segments.map((s) => (s.id === segment.id ? segment : s)) };
}

/** Where a segment dragged to output time `t` would land (its index after the move). */
export function dropIndex(edl: Edl, movingId: string, t: number): number {
  const others = layout(edl.segments.filter((s) => s.id !== movingId));
  return others.filter((p) => (p.ownStart + p.ownEnd) / 2 < t).length;
}

/** Longest transition allowed into segment `index`: half of it or of the one before. */
export function maxTransition(edl: Edl, index: number): number {
  const placed = layout(edl.segments.map((s) => ({ ...s, transition: null })));
  if (index < 1 || index >= placed.length) return 0;
  const a = placed[index - 1];
  const b = placed[index];
  return Math.min(a.end - a.start, b.end - b.start, 10) / 2;
}

const round = (t: number) => Math.round(t * 1000) / 1000;
