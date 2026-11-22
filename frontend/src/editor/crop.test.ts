import { describe, expect, it } from "vitest";
import { addZoom, cropAt, cropWindow, facecamWindow, panCrop, pipBox, setCropAt, updateZoom, zoomAt } from "./crop";
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
    zooms: [],
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

describe("zoomAt (mirrors test_render_planning.py)", () => {
  const zoomed = (split: boolean): Edl => ({
    aspect: "9:16",
    crop: { x: 0.5, y: 0.5, scale: 1 },
    split_screen: split,
    tracking: null,
    ranges: [
      { start: 10, end: 14 },
      { start: 20, end: 26 },
    ],
    captions: { words: [], style: "clean" },
    overlays: [],
    music: null,
    zooms: [
      { start: 10, end: 12, scale: 1.2, ramp: 1 },
      { start: 13, end: 21, scale: 1.3, ramp: 0 },
      { start: 15, end: 18, scale: 1.5, ramp: 0 },
    ],
  });

  it("punches and ramps", () => {
    const edl = zoomed(false);
    expect(zoomAt(edl, 9.9)).toBe(1);
    expect(zoomAt(edl, 10)).toBe(1);
    expect(zoomAt(edl, 10.5)).toBeCloseTo(1.1);
    expect(zoomAt(edl, 11.5)).toBeCloseTo(1.2);
    expect(zoomAt(edl, 12)).toBe(1); // end is exclusive
    expect(zoomAt(edl, 13)).toBe(1.3);
    expect(zoomAt(zoomed(true), 13)).toBe(1);
  });

  it("adds zooms in free space only and keeps them in order", () => {
    const edl = { ...zoomed(false), zooms: [{ start: 12, end: 13, scale: 1.3, ramp: 0 }] };
    const added = addZoom(edl, 11, 26)!;
    expect(added.zooms.map((z) => [z.start, z.end])).toEqual([
      [11, 12],
      [12, 13],
    ]);
    expect(addZoom(edl, 12.5, 26)).toBeNull(); // inside a zoom
    expect(addZoom(edl, 25.9, 26)).toBeNull(); // no room before the end
  });

  it("updates stay between the neighbours", () => {
    const edl = {
      ...zoomed(false),
      zooms: [
        { start: 10, end: 11, scale: 1.2, ramp: 0 },
        { start: 12, end: 13, scale: 1.2, ramp: 0 },
      ],
    };
    expect(updateZoom(edl, 1, { start: 10.5 }).zooms[1].start).toBe(11);
    expect(updateZoom(edl, 1, { scale: 3 }).zooms[1].scale).toBe(2);
    expect(updateZoom(edl, 1, { end: 12.1 })).toBe(edl); // too short: unchanged
  });
});

describe("streamer mode", () => {
  // Mirrors test_render_planning.py (pip_box / streamer mode).
  it("pipBox sits bottom right at 4:3", () => {
    expect(pipBox("9:16")).toEqual({ x: 605, y: 1553, width: 432, height: 324 });
    expect(pipBox("16:9")).toEqual({ x: 1445, y: 713, width: 432, height: 324 });
  });

  it("facecamWindow is the box's aspect, zoomed and kept inside the source", () => {
    const w = facecamWindow(1920, 1080, "9:16", { x: 0.9, y: 0.9, scale: 4 });
    // The backend rounds to even pixels: (1548, 810, 360, 270).
    expect(w.width).toBeCloseTo(360);
    expect(w.height).toBeCloseTo(270);
    expect(w.x).toBeCloseTo(1548);
    expect(w.y).toBeCloseTo(810);
  });
});
