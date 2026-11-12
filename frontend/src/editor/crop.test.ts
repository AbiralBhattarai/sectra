import { describe, expect, it } from "vitest";
import { cropAt, cropWindow, panCrop, reframeCommands } from "./crop";
import { layout } from "./sequence";
import type { Edl, VideoSegment } from "./types";

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

describe("cropAt / reframeCommands (mirrors test_render_planning.py)", () => {
  const segment = (fields: Partial<VideoSegment> = {}): VideoSegment => ({
    id: "s1",
    kind: "video",
    media: null,
    start: 10,
    end: 14,
    speed: 1,
    volume: 1,
    audio_fade_in: 0,
    audio_fade_out: 0,
    color: { brightness: 1, contrast: 1, saturation: 1, sepia: 0, hue: 0 },
    crop: null,
    crop_to: null,
    transition: null,
    ...fields,
  });
  const edl = (enabled: boolean, seg = segment()): Edl => ({
    version: 2,
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
    segments: [seg],
    captions: { words: [], style: "clean" },
    overlays: [],
    broll: [],
    markers: [],
    music: null,
    fade_in: 0,
    fade_out: 0,
  });

  it("follows the shot and keeps the shared zoom", () => {
    const s = segment();
    expect(cropAt(edl(true), s, 9)).toEqual({ x: 0.2, y: 0.5, scale: 2 });
    expect(cropAt(edl(true), s, 12)).toEqual({ x: 0.8, y: 0.5, scale: 2 });
    expect(cropAt(edl(true), s, 5)).toEqual({ x: 0.2, y: 0.5, scale: 2 });
    expect(cropAt(edl(false), s, 12)).toEqual({ x: 0.5, y: 0.5, scale: 2 });
  });

  it("a segment crop overrides tracking and Ken Burns interpolates", () => {
    const own = segment({ crop: { x: 0.1, y: 0.5, scale: 1 }, crop_to: { x: 0.3, y: 0.5, scale: 3 } });
    const c = cropAt(edl(true, own), own, 12);
    expect(c.x).toBeCloseTo(0.2);
    expect(c.scale).toBeCloseTo(2);
  });

  it("reframing goes to the shot, the segment's framing or the clip's", () => {
    const placed = layout([segment()]);
    const crop = { x: 0.7, y: 0.4, scale: 1.5 };
    expect(reframeCommands(edl(true), placed[0], 3, crop)).toEqual([
      { op: "reframe_shot", index: 1, x: 0.7, y: 0.4 },
      { op: "update_clip", crop: { x: 0.5, y: 0.5, scale: 1.5 } },
    ]);
    expect(reframeCommands(edl(false), placed[0], 3, crop)).toEqual([{ op: "update_clip", crop }]);
    const own = segment({ crop: { x: 0.5, y: 0.5, scale: 1 }, crop_to: { x: 0.5, y: 0.5, scale: 2 } });
    const ownPlaced = layout([own]);
    expect(reframeCommands(edl(true, own), ownPlaced[0], 1, crop)).toEqual([
      { op: "update_segment", segment_ids: ["s1"], crop },
    ]);
    expect(reframeCommands(edl(true, own), ownPlaced[0], 3, crop)).toEqual([
      { op: "update_segment", segment_ids: ["s1"], crop_to: crop },
    ]);
  });
});
