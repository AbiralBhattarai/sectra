import { HOLD_SECONDS, paginate } from "./captions";
import type { CaptionStyle, Edl, Segment, Word } from "./types";

/** The main track's timeline: where each segment plays in the output, and how output
 * time maps back to media time. Mirrors backend domain/services/sequence.py. */

export const EPSILON = 1e-6;
/** Matches the backend's MIN_SEGMENT_SECONDS: the shortest segment. */
export const MIN_SEGMENT = 0.1;

/** A segment on the output timeline. */
export interface Placed {
  index: number;
  segment: Segment;
  /** Output time it starts and ends, overlaps with its neighbours' transitions included. */
  start: number;
  end: number;
  /** The part it "owns": each transition is split at its midpoint. */
  ownStart: number;
  ownEnd: number;
}

export function segmentLength(segment: Segment): number {
  return segment.kind === "video" ? (segment.end - segment.start) / segment.speed : segment.duration;
}

/** Seconds segment `index` overlaps the one before it. */
export function transitionIn(segments: Segment[], index: number): number {
  const transition = segments[index]?.transition;
  return index > 0 && transition ? transition.duration : 0;
}

export function layout(segments: Segment[]): Placed[] {
  const placed: Placed[] = [];
  let elapsed = 0;
  segments.forEach((segment, index) => {
    const overlap = transitionIn(segments, index);
    const start = elapsed - overlap;
    const end = start + segmentLength(segment);
    const nextOverlap = transitionIn(segments, index + 1);
    placed.push({ index, segment, start, end, ownStart: start + overlap / 2, ownEnd: end - nextOverlap / 2 });
    elapsed = end;
  });
  return placed;
}

export function outputDuration(segments: Segment[]): number {
  const placed = layout(segments);
  return placed.length ? placed[placed.length - 1].end : 0;
}

/** The segment owning output time `t` (the last one at the very end). */
export function placedAt(placed: Placed[], t: number): Placed | null {
  for (const p of placed) if (p.ownStart <= t && t < p.ownEnd) return p;
  const last = placed[placed.length - 1];
  return last && Math.abs(t - last.ownEnd) < EPSILON ? last : null;
}

/** Segments on screen at output time `t`: one, or two during a transition. */
export function activeAt(placed: Placed[], t: number): Placed[] {
  return placed.filter((p) => p.start <= t && t < p.end);
}

/** Media time at output time `t` inside `p`: source seconds for video and freeze
 * segments, seconds into the image for images. */
export function mediaTime(p: Placed, t: number): number {
  const segment = p.segment;
  const local = Math.min(Math.max(t - p.start, 0), segmentLength(segment));
  if (segment.kind === "video") return segment.start + local * segment.speed;
  if (segment.kind === "freeze") return segment.at;
  return local;
}

/** Where source time `sourceT` of a video segment plays in the output. */
export function outputTime(p: Placed, sourceT: number): number {
  const segment = p.segment;
  return segment.kind === "video" ? p.start + (sourceT - segment.start) / segment.speed : p.start;
}

/** Shows the clip's own video, so captions, tracking and split screen apply. */
export function isClipVideo(segment: Segment): boolean {
  return segment.kind !== "image" && segment.media === null;
}

export function wordsInside(words: Word[], start: number, end: number): Word[] {
  return words.filter((w) => w.start >= start - EPSILON && w.end <= end + EPSILON);
}

/** A caption page on the output timeline; `end` includes the hold. Words keep their
 * index into `edl.captions.words`. */
export interface Cue {
  words: (Word & { index: number })[];
  start: number;
  end: number;
}

const round3 = (t: number) => Math.round(t * 1000) / 1000;

/** Caption pages on the output timeline: each clip-video segment paginates the words
 * inside it on its own and its pages are cut to the part of the timeline it owns. The
 * renderer (sequence.caption_cues) produces the same cues. */
export function captionCues(edl: Edl, style: CaptionStyle): Cue[] {
  const cues: Cue[] = [];
  const all = edl.captions.words;
  for (const p of layout(edl.segments)) {
    const segment = p.segment;
    if (segment.kind !== "video" || segment.media !== null) continue;
    const words = wordsInside(all, segment.start, segment.end);
    const pages = paginate(words, style);
    const out = (t: number) => round3(Math.min(Math.max(outputTime(p, t), p.ownStart), p.ownEnd));
    pages.forEach((page, index) => {
      const next = pages[index + 1];
      const hide = Math.min(page.end + HOLD_SECONDS, next ? next.start : Infinity);
      const start = out(page.start);
      const end = out(Math.min(hide, segment.end));
      if (end - start < 1e-3) return;
      cues.push({
        words: page.words.map((w) => ({ ...w, index: all.indexOf(w), start: out(w.start), end: out(w.end) })),
        start,
        end,
      });
    });
  }
  return cues;
}

export function cueAt(cues: Cue[], t: number): Cue | null {
  return cues.find((c) => c.start <= t && t < c.end) ?? null;
}

/** Output times where the picture changes segment (the middle of each transition). */
export function cutTimes(placed: Placed[]): number[] {
  return placed.slice(1).map((p) => p.ownStart);
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}
