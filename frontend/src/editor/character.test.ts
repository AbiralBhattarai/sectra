// Mirrors backend/tests/unit/test_character_timeline.py — keep the cases identical.
import { describe, expect, it } from "vitest";
import { blinking, blinkStarts, bobAt, characterBox, characterState, mouthAt } from "./character";
import type { CharacterTrack, MouthCue } from "./types";

const CUES: MouthCue[] = [
  { start: 0.0, end: 0.3, shape: "X" },
  { start: 0.3, end: 0.5, shape: "B" },
  { start: 0.5, end: 0.9, shape: "D" },
];

const track = (patch: Partial<CharacterTrack> = {}): CharacterTrack => ({
  name: "guy",
  x: 0.5,
  y: 0.78,
  scale: 0.42,
  enabled: true,
  moods: [],
  ...patch,
});

describe("character timeline", () => {
  it("box is centred and even sized", () => {
    expect(characterBox("9:16", track())).toEqual([271, 1095, 538, 806]);
    expect(characterBox("1:1", track({ scale: 0.5, x: 0.2 }))).toEqual([36, 572, 360, 540]);
  });

  it("mouth follows cues and rests outside them", () => {
    expect(mouthAt(CUES, 0.0)).toBe("X");
    expect(mouthAt(CUES, 0.35)).toBe("B");
    expect(mouthAt(CUES, 0.5)).toBe("D");
    expect(mouthAt(CUES, 0.95)).toBe("X");
    expect(mouthAt([], 1.0)).toBe("X");
  });

  it("blinks are deterministic, two to five seconds apart", () => {
    const starts = blinkStarts(30);
    expect(starts.slice(0, 3)).toEqual([2.0, 6.762, 9.63]);
    let previous = 0;
    for (const start of starts) {
      expect(start - previous).toBeGreaterThanOrEqual(2);
      expect(start - previous).toBeLessThanOrEqual(5);
      previous = start;
    }
    expect(blinking(starts, 2.05)).toBe(true);
    expect(blinking(starts, 2.2)).toBe(false);
    expect(blinking(starts, 1.0)).toBe(false);
  });

  it("bob is a gentle sine", () => {
    expect(bobAt(0)).toBe(0);
    expect(bobAt(0.5)).toBeCloseTo(0.008);
    expect(bobAt(1.5)).toBeCloseTo(-0.008);
  });

  it("state combines mood, mouth and blink", () => {
    const moods = [{ start: 0.4, end: 3, emotion: "shocked" as const }];
    const state = characterState(CUES, moods, blinkStarts(10), 0.6);
    expect([state.expression, state.mouth, state.blink]).toEqual(["shocked", "D", false]);
    expect(characterState(CUES, moods, [], 3.5).expression).toBe("neutral");
  });
});
