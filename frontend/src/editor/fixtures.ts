import type { Color, Edl, Segment, VideoSegment, Word } from "./types";

/** Builders shared by the editor's tests. */

export const NEUTRAL: Color = { brightness: 1, contrast: 1, saturation: 1, sepia: 0, hue: 0 };

export function seg(start: number, end: number, fields: Partial<VideoSegment> = {}): VideoSegment {
  return {
    id: `x${start}-${end}`,
    kind: "video",
    media: null,
    start,
    end,
    speed: 1,
    volume: 1,
    audio_fade_in: 0,
    audio_fade_out: 0,
    color: NEUTRAL,
    crop: null,
    crop_to: null,
    transition: null,
    ...fields,
  };
}

export function words(...specs: [string, number, number][]): Word[] {
  return specs.map(([text, start, end]) => ({ text, start, end }));
}

export function edl(segments: Segment[], fields: Partial<Edl> = {}): Edl {
  return {
    version: 2,
    aspect: "9:16",
    crop: { x: 0.5, y: 0.5, scale: 1 },
    split_screen: false,
    tracking: null,
    segments,
    captions: { words: [], style: "clean" },
    overlays: [],
    broll: [],
    markers: [],
    music: null,
    fade_in: 0,
    fade_out: 0,
    ...fields,
  };
}
