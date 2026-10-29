import type { Edl, Overlay, Span, Word } from "./types";

/** Matches the backend's MIN_RANGE_SECONDS. */
export const MIN_RANGE = 0.1;

const inside = (t: number, ranges: Span[]) => ranges.some((r) => t >= r.start && t <= r.end);
const wordInside = (w: Word, ranges: Span[]) =>
  ranges.some((r) => w.start >= r.start - 1e-6 && w.end <= r.end + 1e-6);

/** Move one edge of range `index`, clamped to the source, its neighbours and MIN_RANGE. */
export function trimRange(
  edl: Edl,
  index: number,
  edge: "start" | "end",
  time: number,
  duration: number,
  transcript: Word[],
): Edl {
  const range = edl.ranges[index];
  const previous = edl.ranges[index - 1];
  const next = edl.ranges[index + 1];
  const moved =
    edge === "start"
      ? { ...range, start: clamp(time, previous?.end ?? 0, range.end - MIN_RANGE) }
      : { ...range, end: clamp(time, range.start + MIN_RANGE, next?.start ?? duration) };
  return withRanges(edl, edl.ranges.map((r, i) => (i === index ? moved : r)), transcript);
}

/** Split the range containing `time` in two; no-op when `time` isn't strictly inside one
 * (or a half would be shorter than MIN_RANGE). */
export function splitAt(edl: Edl, time: number): Edl {
  const index = edl.ranges.findIndex(
    (r) => time - r.start >= MIN_RANGE && r.end - time >= MIN_RANGE,
  );
  if (index === -1) return edl;
  const range = edl.ranges[index];
  const ranges = [
    ...edl.ranges.slice(0, index),
    { start: range.start, end: time },
    { start: time, end: range.end },
    ...edl.ranges.slice(index + 1),
  ];
  return { ...edl, ranges };
}

/** Remove range `index`; a clip always keeps at least one range. */
export function deleteRange(edl: Edl, index: number): Edl {
  if (edl.ranges.length <= 1) return edl;
  const ranges = edl.ranges.filter((_, i) => i !== index);
  return { ...edl, ranges, captions: { ...edl.captions, words: keepWords(edl.captions.words, ranges) } };
}

/** New ranges, with captions following them: edited words that are still kept stay
 * as they are; stretches that just became kept are filled from the transcript. */
export function withRanges(edl: Edl, ranges: Span[], transcript: Word[]): Edl {
  const kept = keepWords(edl.captions.words, ranges);
  const added = transcript.filter((w) => wordInside(w, ranges) && !inside((w.start + w.end) / 2, edl.ranges));
  const words = [...kept, ...added].sort((a, b) => a.start - b.start);
  return { ...edl, ranges, captions: { ...edl.captions, words } };
}

function keepWords(words: Word[], ranges: Span[]): Word[] {
  return words.filter((w) => wordInside(w, ranges));
}

/** Length of the rendered clip. */
export function outputDuration(ranges: Span[]): number {
  return ranges.reduce((total, r) => total + (r.end - r.start), 0);
}

/** Where source time `t` lands in the rendered clip (gaps collapse onto the next range). */
export function sourceToOutput(t: number, ranges: Span[]): number {
  let elapsed = 0;
  for (const r of ranges) {
    if (t < r.start) return elapsed;
    if (t <= r.end) return elapsed + (t - r.start);
    elapsed += r.end - r.start;
  }
  return elapsed;
}

/** Source time shown at output time `o`. */
export function outputToSource(o: number, ranges: Span[]): number {
  let remaining = Math.max(0, o);
  for (const r of ranges) {
    const length = r.end - r.start;
    if (remaining <= length) return r.start + remaining;
    remaining -= length;
  }
  return ranges.length ? ranges[ranges.length - 1].end : 0;
}

/** Where playback at source time `t` should be: `t` itself inside a kept range, the
 * start of the next range when in a cut, or null once past the last range. */
export function nextPlayable(t: number, ranges: Span[]): number | null {
  for (const r of ranges) {
    if (t < r.start) return r.start;
    if (t < r.end) return t;
  }
  return null;
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

export const DEFAULT_OVERLAY_SECONDS = 3;

/** A new overlay at output time `at`, fitted inside the clip. */
export function newOverlay(at: number, clipDuration: number): Overlay {
  const length = Math.min(DEFAULT_OVERLAY_SECONDS, clipDuration);
  const start = clamp(at, 0, Math.max(0, clipDuration - length));
  return { text: "Your text here", start, end: start + length, x: 0.5, y: 0.12, style: "title" };
}

/** Overlays on screen at output time `t`. */
export function overlaysAt(overlays: Overlay[], t: number): number[] {
  return overlays.flatMap((o, index) => (t >= o.start && t < o.end ? [index] : []));
}
