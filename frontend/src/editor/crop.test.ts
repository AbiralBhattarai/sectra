import { describe, expect, it } from "vitest";
import { cropWindow, panCrop } from "./crop";

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
});

describe("panCrop", () => {
  it("dragging the picture right moves the window left", () => {
    // Frame is 270 px wide showing a 607.5 px wide window: 1 frame px = 2.25 source px.
    const moved = panCrop(centre, 100, 0, 270, 480, 1920, 1080, 9 / 16);
    expect(moved.x).toBeCloseTo(0.5 - (100 * 2.25) / 1920);
    expect(moved.y).toBe(0.5);
  });
});
