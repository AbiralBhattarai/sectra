/** What the narrator character looks like at a given moment. Mirrors the backend's
 * domain/services/character_timeline.py — change both together (the tests are mirrored),
 * or the export won't match the preview. */
import { OUTPUT_SIZES } from "./crop";
import type { AspectRatio, CharacterTrack, Emotion, Mood, MouthCue } from "./types";

/** Every character's layers share one canvas of this width:height (1000×1500). */
export const CANVAS_ASPECT = 2 / 3;
/** Rest mouth, between cues and when there is no lip sync. */
export const REST = "X";
export const BLINK_SECONDS = 0.12;
const BLINK_MIN = 2.0;
const BLINK_SPREAD = 3.0;
// Park–Miller: exact in JS doubles (products stay below 2^53) and in Python ints.
const PM_MODULUS = 2147483647;
const PM_MULTIPLIER = 16807;
const PM_SEED = 7;
export const BOB_AMPLITUDE = 0.008;
export const BOB_HZ = 0.5;

export interface CharacterState {
  expression: Emotion;
  mouth: string;
  blink: boolean;
  /** Vertical offset as a fraction of the box height (positive = down). */
  bob: number;
}

/** [x, y, width, height] of the character's box in output pixels. */
export function characterBox(aspect: AspectRatio, track: CharacterTrack): [number, number, number, number] {
  const [outWidth, outHeight] = OUTPUT_SIZES[aspect];
  const height = even(track.scale * outHeight);
  const width = even(height * CANVAS_ASPECT);
  const x = Math.floor(track.x * outWidth - width / 2 + 0.5);
  const y = Math.floor(track.y * outHeight - height / 2 + 0.5);
  return [x, y, width, height];
}

/** The mouth shape at source time `t`; cues are sorted and non-overlapping. */
export function mouthAt(cues: MouthCue[], t: number): string {
  let low = 0;
  let high = cues.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (cues[mid].start <= t) low = mid + 1;
    else high = mid;
  }
  const index = low - 1;
  return index >= 0 && t < cues[index].end ? cues[index].shape : REST;
}

export function moodAt(moods: Mood[], t: number): Emotion {
  for (const mood of moods) if (mood.start <= t && t < mood.end) return mood.emotion;
  return "neutral";
}

/** Source times at which the character blinks, from 0 up to `until`. */
export function blinkStarts(until: number): number[] {
  const starts: number[] = [];
  let seed = PM_SEED;
  let t = 0;
  for (;;) {
    seed = (seed * PM_MULTIPLIER) % PM_MODULUS;
    t += BLINK_MIN + (BLINK_SPREAD * seed) / PM_MODULUS;
    if (t > until) return starts;
    starts.push(round3(t));
  }
}

export function blinking(starts: number[], t: number): boolean {
  let index = -1;
  for (let i = 0; i < starts.length && starts[i] <= t; i++) index = i;
  return index >= 0 && t < starts[index] + BLINK_SECONDS;
}

export function bobAt(t: number): number {
  return BOB_AMPLITUDE * Math.sin(2 * Math.PI * BOB_HZ * t);
}

export function characterState(cues: MouthCue[], moods: Mood[], blinks: number[], t: number): CharacterState {
  return { expression: moodAt(moods, t), mouth: mouthAt(cues, t), blink: blinking(blinks, t), bob: bobAt(t) };
}

/** Python's round(x, 3) for the values we produce (no exact .5 ties in practice). */
function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function even(value: number): number {
  return Math.max(2, Math.floor(value / 2 + 0.5) * 2);
}
