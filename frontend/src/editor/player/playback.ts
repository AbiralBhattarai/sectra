import type { CSSProperties } from "react";
import { transitionIn, type Placed } from "../sequence";
import type { Color, Edl, TransitionType } from "../types";

/** Pure rules of the preview player (see Player.tsx). */

/** Main-track segments alternate between two players, so the one coming next is always
 * loaded on the other — gapless cuts, and both visible during a transition. Each slot
 * shows its active segment, else preloads its next one. */
export interface SlotTarget {
  placed: Placed;
  active: boolean;
}

export function slotTargets(placed: Placed[], t: number): [SlotTarget | null, SlotTarget | null] {
  const targets: [SlotTarget | null, SlotTarget | null] = [null, null];
  for (const slot of [0, 1] as const) {
    const mine = placed.filter((p) => p.index % 2 === slot);
    const active = mine.find((p) => p.start <= t && t < p.end);
    const upcoming = mine.find((p) => p.start > t);
    const last = mine[mine.length - 1];
    // At the very end, keep showing the last frame.
    const fallback = !upcoming && last && t >= last.end && last.index === placed.length - 1 ? last : undefined;
    const target = active ?? upcoming ?? fallback;
    if (target) targets[slot] = { placed: target, active: !!active || target === fallback };
  }
  return targets;
}

/** The CSS `filter` of a grade, in the same order the renderer applies it. */
export function colorFilter(color: Color): string | undefined {
  const { brightness, contrast, saturation, sepia, hue } = color;
  if (brightness === 1 && contrast === 1 && saturation === 1 && sepia === 0 && hue === 0) return undefined;
  return `brightness(${brightness}) contrast(${contrast}) saturate(${saturation}) sepia(${sepia}) hue-rotate(${hue}deg)`;
}

export interface TransitionLook {
  incoming: CSSProperties;
  outgoing: CSSProperties;
  /** A colour washed over both (fade through black/white). */
  wash?: { color: string; opacity: number };
}

/** How the two segments of a transition look `q` (0..1) of the way through. An
 * approximation of ffmpeg's xfade, close enough to judge timing and direction. */
export function transitionLook(type: TransitionType, q: number): TransitionLook {
  const pct = (v: number) => `${v * 100}%`;
  switch (type) {
    case "fadeblack":
    case "fadewhite":
      return {
        incoming: { opacity: q < 0.5 ? 0 : 1 },
        outgoing: {},
        wash: { color: type === "fadeblack" ? "#000" : "#fff", opacity: 1 - Math.abs(2 * q - 1) },
      };
    case "wipeleft":
      return { incoming: { clipPath: `inset(0 0 0 ${pct(1 - q)})` }, outgoing: {} };
    case "wiperight":
      return { incoming: { clipPath: `inset(0 ${pct(1 - q)} 0 0)` }, outgoing: {} };
    case "wipeup":
      return { incoming: { clipPath: `inset(${pct(1 - q)} 0 0 0)` }, outgoing: {} };
    case "wipedown":
      return { incoming: { clipPath: `inset(0 0 ${pct(1 - q)} 0)` }, outgoing: {} };
    case "slideleft":
      return { incoming: { transform: `translateX(${pct(1 - q)})` }, outgoing: { transform: `translateX(${pct(-q)})` } };
    case "slideright":
      return { incoming: { transform: `translateX(${pct(q - 1)})` }, outgoing: { transform: `translateX(${pct(q)})` } };
    case "slideup":
      return { incoming: { transform: `translateY(${pct(1 - q)})` }, outgoing: { transform: `translateY(${pct(-q)})` } };
    case "slidedown":
      return { incoming: { transform: `translateY(${pct(q - 1)})` }, outgoing: { transform: `translateY(${pct(q)})` } };
    case "circleopen":
      return { incoming: { clipPath: `circle(${pct(q * 0.75)} at 50% 50%)` }, outgoing: {} };
    case "zoomin":
      return { incoming: { opacity: q }, outgoing: { transform: `scale(${1 + q})`, opacity: 1 - q } };
    default: // fade, dissolve, pixelize
      return { incoming: { opacity: q }, outgoing: {} };
  }
}

/** Progress (0..1) of the transition into `p` at output time `t`, or null outside it. */
export function transitionProgress(segments: Edl["segments"], p: Placed, t: number): number | null {
  const d = transitionIn(segments, p.index);
  return d > 0 && t >= p.start && t < p.start + d ? (t - p.start) / d : null;
}

/** Gain of a segment's sound at output time `t`: its volume shaped by its own fades,
 * crossfades with its neighbours and the clip's fade in/out. Stills are silent. */
export function segmentGain(edl: Edl, p: Placed, t: number, duration: number): number {
  const segment = p.segment;
  if (segment.kind !== "video") return 0;
  const local = t - p.start;
  const length = p.end - p.start;
  let gain = segment.volume;
  if (segment.audio_fade_in > 0) gain *= Math.min(1, local / segment.audio_fade_in);
  if (segment.audio_fade_out > 0) gain *= Math.min(1, (length - local) / segment.audio_fade_out);
  const fadeIn = transitionIn(edl.segments, p.index);
  if (fadeIn > 0) gain *= Math.min(1, local / fadeIn);
  const fadeOut = transitionIn(edl.segments, p.index + 1);
  if (fadeOut > 0) gain *= Math.min(1, (length - local) / fadeOut);
  return Math.max(0, gain * clipFade(edl, t, duration));
}

/** 0..1 multiplier of the whole clip's fade in/out (picture to black, sound to silence). */
export function clipFade(edl: Edl, t: number, duration: number): number {
  let f = 1;
  if (edl.fade_in > 0) f = Math.min(f, t / edl.fade_in);
  if (edl.fade_out > 0) f = Math.min(f, (duration - t) / edl.fade_out);
  return Math.min(Math.max(f, 0), 1);
}
