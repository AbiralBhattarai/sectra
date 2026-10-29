/** Mirrors the backend `Edl` (domain/models/edl.py). Times are seconds on the source
 * timeline, except overlays, which are on the clip's output timeline. */

export type AspectRatio = "9:16" | "1:1" | "16:9";
export type CaptionStyle = "bold-highlight" | "clean" | "boxed" | "none";
export type OverlayStyle = "title" | "label";

export interface Span {
  start: number;
  end: number;
}

export interface Word {
  text: string;
  start: number;
  end: number;
  probability?: number | null;
}

export interface Crop {
  /** Centre of the crop window as fractions of the source frame. */
  x: number;
  y: number;
  /** Zoom; 1 = the largest window of the target aspect that fits the source. */
  scale: number;
}

/** Free-positioned text. Unlike everything else, times are on the clip's output timeline. */
export interface Overlay {
  text: string;
  start: number;
  end: number;
  /** Centre of the text as fractions of the frame. */
  x: number;
  y: number;
  style: OverlayStyle;
}

export interface Music {
  file: string;
  volume: number;
  duck: boolean;
}

export interface Edl {
  aspect: AspectRatio;
  crop: Crop;
  ranges: Span[];
  captions: { words: Word[]; style: CaptionStyle };
  overlays: Overlay[];
  music: Music | null;
}

export interface ClipDetail {
  id: string;
  video_id: string;
  title: string;
  hook: string;
  score: number;
  reason: string;
  start: number;
  end: number;
  created_at: string;
  updated_at: string;
  edl: Edl;
}

export interface Transcript {
  language: string | null;
  segments: { id: number; start: number; end: number; text: string; words: Word[] }[];
}

export interface SpeechMap {
  duration: number;
  segments: Span[];
}

export interface Peaks {
  per_second: number;
  peaks: number[];
}

export const ASPECTS: Record<AspectRatio, number> = { "9:16": 9 / 16, "1:1": 1, "16:9": 16 / 9 };

export interface MusicTrack {
  file: string;
  name: string;
  artist: string | null;
  mood: string | null;
  /** Part of Sectra's built-in CC0 library rather than uploaded. */
  default: boolean;
}
