import { describe, expect, it } from "vitest";
import {
  deleteRange,
  newOverlay,
  nextPlayable,
  overlaysAt,
  outputDuration,
  outputToSource,
  sourceToOutput,
  splitAt,
  trimRange,
  withRanges,
} from "./edlOps";
import type { Edl, Word } from "./types";

const word = (text: string, start: number, end: number): Word => ({ text, start, end });

/** One word per second, "w0" at 0-0.5, "w1" at 1-1.5, … */
const TRANSCRIPT = Array.from({ length: 60 }, (_, i) => word(`w${i}`, i, i + 0.5));

function edl(ranges: [number, number][]): Edl {
  const spans = ranges.map(([start, end]) => ({ start, end }));
  return {
    aspect: "9:16",
    crop: { x: 0.5, y: 0.5, scale: 1 },
    ranges: spans,
    captions: {
      style: "bold-highlight",
      words: TRANSCRIPT.filter((w) => spans.some((r) => w.start >= r.start && w.end <= r.end)),
    },
    overlays: [],
    music: null,
  };
}

const texts = (e: Edl) => e.captions.words.map((w) => w.text);

describe("trimRange", () => {
  it("extending pulls the newly kept words from the transcript", () => {
    const result = trimRange(edl([[10, 13]]), 0, "end", 15, 60, TRANSCRIPT);
    expect(result.ranges).toEqual([{ start: 10, end: 15 }]);
    expect(texts(result)).toEqual(["w10", "w11", "w12", "w13", "w14"]);
  });

  it("keeps caption edits in the part that stays", () => {
    const base = edl([[10, 13]]);
    base.captions.words[1] = { ...base.captions.words[1], text: "EDITED" };
    const result = trimRange(base, 0, "start", 11, 60, TRANSCRIPT);
    expect(texts(result)).toEqual(["EDITED", "w12"]);
  });

  it("stops at the neighbouring range and keeps a minimum length", () => {
    const base = edl([[0, 5], [10, 20]]);
    expect(trimRange(base, 1, "start", 2, 60, TRANSCRIPT).ranges[1].start).toBe(5);
    expect(trimRange(base, 1, "start", 30, 60, TRANSCRIPT).ranges[1].start).toBeCloseTo(19.9);
    expect(trimRange(base, 1, "end", 99, 60, TRANSCRIPT).ranges[1].end).toBe(60);
  });
});

describe("splitAt / deleteRange", () => {
  it("splits the range under the playhead", () => {
    expect(splitAt(edl([[10, 20]]), 14).ranges).toEqual([
      { start: 10, end: 14 },
      { start: 14, end: 20 },
    ]);
  });

  it("ignores splits on an edge or in a cut", () => {
    const base = edl([[10, 20], [30, 40]]);
    expect(splitAt(base, 10)).toBe(base);
    expect(splitAt(base, 25)).toBe(base);
  });

  it("split then delete cuts a section out, captions included", () => {
    const cut = deleteRange(splitAt(splitAt(edl([[10, 20]]), 13), 15), 1);
    expect(cut.ranges).toEqual([
      { start: 10, end: 13 },
      { start: 15, end: 20 },
    ]);
    expect(texts(cut)).toEqual(["w10", "w11", "w12", "w15", "w16", "w17", "w18", "w19"]);
  });

  it("never deletes the last range", () => {
    const base = edl([[10, 20]]);
    expect(deleteRange(base, 0)).toBe(base);
  });

  it("withRanges re-adds a region that was cut earlier", () => {
    const cut = edl([[10, 12], [15, 18]]);
    const result = withRanges(cut, [{ start: 10, end: 18 }], TRANSCRIPT);
    expect(texts(result)).toEqual(["w10", "w11", "w12", "w13", "w14", "w15", "w16", "w17"]);
  });
});

describe("time mapping", () => {
  const ranges = [
    { start: 10, end: 14 },
    { start: 20, end: 26 },
  ];

  it("output duration sums the ranges", () => {
    expect(outputDuration(ranges)).toBe(10);
  });

  it("maps source to output and back", () => {
    expect(sourceToOutput(12, ranges)).toBe(2);
    expect(sourceToOutput(17, ranges)).toBe(4); // in the cut: collapses onto the next range
    expect(sourceToOutput(21, ranges)).toBe(5);
    expect(outputToSource(5, ranges)).toBe(21);
    expect(outputToSource(99, ranges)).toBe(26);
  });

  it("playback skips cuts and stops after the last range", () => {
    expect(nextPlayable(5, ranges)).toBe(10);
    expect(nextPlayable(12, ranges)).toBe(12);
    expect(nextPlayable(14, ranges)).toBe(20);
    expect(nextPlayable(26, ranges)).toBeNull();
  });
});

describe("overlays", () => {
  it("a new overlay starts at the playhead and fits in the clip", () => {
    expect(newOverlay(4, 20)).toMatchObject({ start: 4, end: 7 });
    expect(newOverlay(19, 20)).toMatchObject({ start: 17, end: 20 });
    expect(newOverlay(0, 2)).toMatchObject({ start: 0, end: 2 });
  });

  it("finds the overlays showing at a time (end exclusive)", () => {
    const overlays = [newOverlay(0, 20), newOverlay(2, 20)];
    expect(overlaysAt(overlays, 1)).toEqual([0]);
    expect(overlaysAt(overlays, 2.5)).toEqual([0, 1]);
    expect(overlaysAt(overlays, 3)).toEqual([1]);
  });
});
