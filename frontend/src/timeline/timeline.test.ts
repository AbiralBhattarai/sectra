import { describe, expect, it } from "vitest";
import { edl, seg } from "../editor/fixtures";
import { dropIndex, maxTransition, trimmed } from "./drafts";
import { snap, snapTargets } from "./snapping";

describe("snapping", () => {
  const clip = edl([seg(0, 4), seg(10, 14)], {
    markers: [{ id: "m", time: 6, label: "" }],
    overlays: [{ id: "o", text: "x", start: 1, end: 2.5, x: 0.5, y: 0.5, style: "title" }],
  });

  it("pulls a time onto a nearby cut, marker or edge", () => {
    const targets = snapTargets(clip, 7.2);
    expect(snap(4.05, targets, 100)).toBe(4); // 5 px away from the cut
    expect(snap(4.2, targets, 100)).toBe(4.2); // 20 px: too far
    expect(snap(6.03, targets, 100)).toBe(6);
    expect(snap(2.48, snapTargets(clip, 0, ["o"]), 100)).toBe(2.48); // its own edge doesn't count
  });
});

describe("drafts", () => {
  it("trims video on the source at its speed, stills by length", () => {
    const fast = seg(10, 20, { speed: 2 }); // plays 0-5 s
    expect(trimmed(fast, "start", 1, 0, 5, null)).toMatchObject({ start: 12, end: 20 });
    expect(trimmed(fast, "end", 4, 0, 5, 18)).toMatchObject({ start: 10, end: 18 });
    expect(trimmed(fast, "end", 9, 0, 5, 18)).toMatchObject({ end: 18 }); // capped at the source
    const still = { ...seg(0, 1), kind: "image", image: "a.png", duration: 3, crop_to: null } as const;
    expect(trimmed(still, "end", 2, 0, 3, null)).toMatchObject({ duration: 2 });
  });

  it("finds where a dragged segment lands and how long a transition may be", () => {
    const clip = edl([seg(0, 2, { id: "a" }), seg(2, 4, { id: "b" }), seg(4, 10, { id: "c" })]);
    expect(dropIndex(clip, "a", 5)).toBe(1); // past b's middle (3 s once a is lifted out)
    expect(dropIndex(clip, "c", 0.5)).toBe(0);
    expect(maxTransition(clip, 2)).toBe(1);
    expect(maxTransition(clip, 0)).toBe(0);
  });
});
