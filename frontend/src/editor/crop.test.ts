import { describe, expect, it } from "vitest";
import { cropAt, cropWindow, panCrop, setCropAt } from "./crop";
import type { Edl } from "./types";

const centre = { x: 0.5, y: 0.5, scale: 1 };

describe("cropWindow", () => {
  it("vertical crop of a landscape source uses the full height", () => {
    expect(cropWindow(1920, 1080, 9 / 16, centre)).toEqual({
      x: 656.25,
      y: 0,
      width: 607.5,
      height: 1080,
    });
  });

  it("zoom shrinks the window and edges clamp it inside the frame", () => {
    const w = cropWindow(1920, 1080, 9 / 16, { x: 0, y: 0.5, scale: 2 });
    expect(w).toEqual({ x: 0, y: 270, width: 303.75, height: 540 });
  });

  it("landscape output of a landscape source is the whole frame", () => {
    expect(cropWindow(1920, 1080, 16 / 9, centre)).toEqual({ x: 0, y: 0, width: 1920, height: 1080 });
  });

  it("split screen frames each 960 px half for half of a 9:16 frame", () => {
    const w = cropWindow(960, 1080, (9 / 16) * 2, centre);
    expect(w.x).toBe(0);
    expect(w.y).toBeCloseTo(113.33);
    expect(w.width).toBe(960);
    expect(w.height).toBeCloseTo(853.33);
  });
});

describe("panCrop", () => {
  it("dragging the picture right moves the window left", () => {
    // Frame is 270 px wide showing a 607.5 px wide window: 1 frame px = 2.25 source px.
    const moved = panCrop(centre, 100, 0, 270, 480, 1920, 1080, 9 / 16);
    expect(moved.x).toBeCloseTo(0.5 - (100 * 2.25) / 1920);
    expect(moved.y).toBe(0.5);
  });
});

describe("cropAt / setCropAt (mirrors test_render_planning.py)", () => {
  const edl = (enabled: boolean): Edl => ({
    aspect: "9:16",
    crop: { x: 0.5, y: 0.5, scale: 2 },
    split_screen: false,
    tracking: {
      enabled,
      span: { start: 8, end: 28 },
      shots: [
        { start: 8, face: 0, x: 0.2, y: 0.5 },
        { start: 12, face: 1, x: 0.8, y: 0.5 },
      ],
    },
    ranges: [{ start: 10, end: 14 }],
    captions: { words: [], style: "clean" },
    overlays: [],
    music: null,
  });

  it("follows the shot and keeps the shared zoom", () => {
    expect(cropAt(edl(true), 9)).toEqual({ x: 0.2, y: 0.5, scale: 2 });
    expect(cropAt(edl(true), 12)).toEqual({ x: 0.8, y: 0.5, scale: 2 });
    expect(cropAt(edl(true), 5)).toEqual({ x: 0.2, y: 0.5, scale: 2 });
    expect(cropAt(edl(false), 12)).toEqual({ x: 0.5, y: 0.5, scale: 2 });
  });

  it("reframing moves only the shot under the playhead; zoom moves all", () => {
    const next = setCropAt(edl(true), 13, { x: 0.7, y: 0.4, scale: 1.5 });
    expect(next.tracking!.shots.map((s) => [s.x, s.y])).toEqual([[0.2, 0.5], [0.7, 0.4]]);
    expect(next.crop).toEqual({ x: 0.5, y: 0.5, scale: 1.5 });
    expect(setCropAt(edl(false), 13, { x: 0.7, y: 0.4, scale: 1 }).crop).toEqual({ x: 0.7, y: 0.4, scale: 1 });
  });
});
