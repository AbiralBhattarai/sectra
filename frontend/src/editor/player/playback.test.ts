import { describe, expect, it } from "vitest";
import { edl, seg } from "../fixtures";
import { layout } from "../sequence";
import { clipFade, colorFilter, segmentGain, slotTargets, transitionLook } from "./playback";

const fade = (duration: number) => ({ type: "fade" as const, duration });

describe("slotTargets", () => {
  const placed = layout([seg(0, 4), seg(10, 14, { transition: fade(1) }), seg(20, 22)]);
  const ids = (t: number) => slotTargets(placed, t).map((s) => s && [s.placed.index, s.active]);

  it("alternates segments between two players and preloads the next", () => {
    expect(ids(1)).toEqual([[0, true], [1, false]]);
    expect(ids(3.5)).toEqual([[0, true], [1, true]]); // in the crossfade
    expect(ids(5)).toEqual([[2, false], [1, true]]);
    expect(ids(8)).toEqual([[2, true], null]);
    expect(ids(9)).toEqual([[2, true], null]); // the end keeps the last frame
  });
});

describe("looks", () => {
  it("grades with the CSS filter the render reproduces", () => {
    expect(colorFilter({ brightness: 1, contrast: 1, saturation: 1, sepia: 0, hue: 0 })).toBeUndefined();
    expect(colorFilter({ brightness: 1.2, contrast: 1, saturation: 0, sepia: 0, hue: -10 })).toBe(
      "brightness(1.2) contrast(1) saturate(0) sepia(0) hue-rotate(-10deg)",
    );
  });

  it("washes through black at the middle of fadeblack", () => {
    expect(transitionLook("fadeblack", 0.5).wash).toEqual({ color: "#000", opacity: 1 });
    expect(transitionLook("wipeleft", 0.25).incoming.clipPath).toBe("inset(0 0 0 75%)");
  });
});

describe("gain", () => {
  const clip = edl([seg(0, 4, { volume: 0.5, audio_fade_in: 1 }), seg(10, 14, { transition: fade(2) })], {
    fade_out: 1,
  });
  const placed = layout(clip.segments);

  it("follows volume, fades and crossfades", () => {
    expect(segmentGain(clip, placed[0], 0.5, 6)).toBeCloseTo(0.25);
    expect(segmentGain(clip, placed[0], 3, 6)).toBeCloseTo(0.25); // 1 s into a 2 s crossfade out
    expect(segmentGain(clip, placed[1], 3, 6)).toBeCloseTo(0.5);
    expect(segmentGain(clip, placed[1], 5.5, 6)).toBeCloseTo(0.5); // clip fade out
    expect(clipFade(clip, 6, 6)).toBe(0);
  });
});
