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

/** Streamer mode: the source region shown in the bottom-right picture-in-picture box
 * (the face cam) while the main frame shows gameplay. Centre as fractions of the source,
 * plus zoom; the box's aspect is fixed (4:3). */
export interface Facecam {
  x: number;
  y: number;
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

/** One camera position chosen by face tracking; runs until the next shot starts. */
export interface Shot {
  /** Source time. */
  start: number;
  /** The tracked face this shot frames (labels only). */
  face: number;
  /** Crop centre as fractions of the source frame; zoom is the shared `Edl.crop.scale`. */
  x: number;
  y: number;
}

/** Active-speaker framing: hard cuts between shots of whoever is talking. */
export interface Tracking {
  /** The checkbox; shots are kept while it is off. */
  enabled: boolean;
  /** Source span the tracker analysed. */
  span: Span;
  /** Sorted by start; the first starts at `span.start`. */
  shots: Shot[];
}

/** A zoom-in on top of the framing, centred on the crop. Source time, like shots. */
export interface Zoom {
  start: number;
  end: number;
  /** Magnification of the framed picture (1–2). */
  scale: number;
  /** Seconds to ease in from 1×; 0 is a hard punch-in. */
  ramp: number;
}

export interface Edl {
  aspect: AspectRatio;
  crop: Crop;
  /** Left and right halves of the source stacked top/bottom (e.g. OmeTV's two cameras);
   * `crop` frames each half the same way. */
  split_screen: boolean;
  tracking: Tracking | null;
  ranges: Span[];
  captions: Captions;
  overlays: Overlay[];
  music: Music | null;
  /** Sorted and non-overlapping; ignored with `split_screen`. */
  zooms: Zoom[];
  /** Streamer mode; when set, split screen and face tracking are ignored. */
  facecam?: Facecam | null;
  /** Stories: the talking narrator, over the picture and under the captions. */
  character?: CharacterTrack | null;
}

export interface Captions {
  words: Word[];
  style: CaptionStyle;
  /** Bottom edge of the caption block as a fraction of the frame height (e.g. above a
   * narrator); null/absent = the style's own position. */
  y?: number | null;
}

export type Emotion = "neutral" | "happy" | "sad" | "angry" | "shocked" | "smug";
export const EMOTIONS: Emotion[] = ["neutral", "happy", "sad", "angry", "shocked", "smug"];

/** The character's expression over a stretch of source time. */
export interface Mood {
  start: number;
  end: number;
  emotion: Emotion;
}

/** The talking narrator: a box centred at (x, y) (fractions of the frame), `scale` of
 * the frame tall. Mirrors the backend `CharacterTrack`. */
export interface CharacterTrack {
  name: string;
  x: number;
  y: number;
  scale: number;
  enabled: boolean;
  moods: Mood[];
}

/** One Rhubarb mouth shape from `start` to `end` (source time). */
export interface MouthCue {
  start: number;
  end: number;
  shape: string;
}

export interface ClipDetail {
  id: string;
  video_id: string;
  title: string;
  hook: string;
  score: number;
  reason: string;
  /** Ready-to-post social caption with hashtags. */
  caption: string;
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
