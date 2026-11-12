import { describe, expect, it } from "vitest";
import { edl, NEUTRAL, seg, words } from "./fixtures";
import { activeAt, captionCues, layout, mediaTime, outputDuration, outputTime, placedAt } from "./sequence";
import type { Edl, Segment } from "./types";

/** Cases mirror backend tests/unit/test_sequence.py. */

const spans = (segments: Segment[]) => layout(segments).map((p) => [round(p.start), round(p.end)]);
const round = (t: number) => Math.round(t * 1000) / 1000;
const freeze = (at: number, duration: number): Segment => ({
  id: "f",
  kind: "freeze",
  media: null,
  at,
  duration,
  color: NEUTRAL,
  crop: null,
  transition: null,
});
const fade = (duration: number) => ({ type: "fade" as const, duration });

describe("layout", () => {
  it("plays segments back to back at their speed", () => {
    const track = [seg(10, 14), seg(20, 26, { speed: 2 }), freeze(30, 1.5)];
    expect(spans(track)).toEqual([[0, 4], [4, 7], [7, 8.5]]);
    expect(outputDuration(track)).toBe(8.5);
  });

  it("overlaps a transition with the previous segment and splits ownership", () => {
    const placed = layout([seg(0, 4), seg(10, 14, { transition: fade(1) }), seg(20, 22)]);
    expect(placed.map((p) => [p.start, p.end])).toEqual([[0, 4], [3, 7], [7, 9]]);
    expect(placed.map((p) => [p.ownStart, p.ownEnd])).toEqual([[0, 3.5], [3.5, 7], [7, 9]]);
    expect(activeAt(placed, 3.2).map((p) => p.index)).toEqual([0, 1]);
  });

  it("ignores the first segment's transition", () => {
    expect(spans([seg(0, 4, { transition: fade(1) })])).toEqual([[0, 4]]);
  });
});

describe("lookups", () => {
  const image: Segment = { id: "i", kind: "image", image: "a.png", duration: 2, color: NEUTRAL, crop: null, crop_to: null, transition: null };
  const placed = layout([seg(10, 14), seg(20, 26, { speed: 2 }), image]);

  it("map between output and media time", () => {
    expect(placedAt(placed, 3.9)?.index).toBe(0);
    expect(placedAt(placed, 4)?.index).toBe(1);
    expect(placedAt(placed, 9)?.index).toBe(2);
    expect(placedAt(placed, 9.5)).toBeNull();
    expect(mediaTime(placed[1], 5)).toBe(22);
    expect(mediaTime(placed[2], 8)).toBe(1);
    expect(outputTime(placed[1], 22)).toBe(5);
  });
});

describe("captionCues", () => {
  const spoken = words(["hello", 10.2, 10.6], ["there.", 10.7, 11.0], ["again", 20.5, 21.0]);
  const clip = (segments: Segment[], style: Edl["captions"]["style"] = "bold-highlight") =>
    edl(segments, { captions: { words: spoken, style } });

  it("follow each segment onto the output timeline", () => {
    const cues = captionCues(clip([seg(10, 12), seg(20, 23)]), "bold-highlight");
    expect(cues.map((c) => c.words.map((w) => [w.text, w.start, w.end]))).toEqual([
      [["hello", 0.2, 0.6], ["there.", 0.7, 1.0]],
      [["again", 2.5, 3.0]],
    ]);
    expect(cues[0].end).toBeCloseTo(1.3);
    expect(cues[1].end).toBeCloseTo(3.3);
    expect(cues[1].words[0].index).toBe(2);
  });

  it("come with reordered, duplicated and sped-up segments", () => {
    const segments = [seg(20, 23, { id: "b", speed: 2 }), seg(10, 12, { id: "a" }), seg(10, 12, { id: "a2" })];
    const cues = captionCues(clip(segments), "clean");
    expect(cues.map((c) => [c.words[0].text, c.start])).toEqual([["again", 0.25], ["hello", 1.7], ["hello", 3.7]]);
    expect(cues[0].words[0].end).toBe(0.5);
  });

  it("are cut at the middle of a transition", () => {
    const [first, second] = captionCues(clip([seg(10, 12), seg(20, 23, { transition: fade(1) })]), "clean");
    expect([first.start, first.end]).toEqual([0.2, 1.3]);
    expect(second.start).toBe(1.5);
  });

  it("skip other media", () => {
    expect(captionCues(clip([seg(10, 12, { media: "00000000-0000-0000-0000-000000000001" })]), "clean")).toEqual([]);
  });
});
