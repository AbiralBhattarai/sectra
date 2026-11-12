/** Mirrors the backend `Edl` (domain/models/edl.py). Segment times are seconds on the
 * segment's video; overlays, B-roll and markers are on the clip's output timeline. */

export type AspectRatio = "9:16" | "1:1" | "16:9";
export type CaptionStyle = "bold-highlight" | "clean" | "boxed" | "none";
export type OverlayStyle = "title" | "label";
export type BrollLayout = "full" | "pip";
export type ColorPreset = "none" | "bw" | "warm" | "cool" | "vivid" | "vintage" | "dramatic";
export type TransitionType =
  | "fade"
  | "dissolve"
  | "fadeblack"
  | "fadewhite"
  | "wipeleft"
  | "wiperight"
  | "wipeup"
  | "wipedown"
  | "slideleft"
  | "slideright"
  | "slideup"
  | "slidedown"
  | "circleopen"
  | "zoomin"
  | "pixelize";

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

/** CSS filter semantics: brightness, contrast, saturate, sepia, hue-rotate (in that order). */
export interface Color {
  brightness: number;
  contrast: number;
  saturation: number;
  sepia: number;
  hue: number;
}

export interface Transition {
  type: TransitionType;
  duration: number;
}

interface SegmentBase {
  id: string;
  color: Color;
  /** Framing for this segment only; null follows `Edl.crop` (or face tracking). */
  crop: Crop | null;
  /** Into this segment from the previous one. */
  transition: Transition | null;
}

export interface VideoSegment extends SegmentBase {
  kind: "video";
  /** null = the clip's own video. */
  media: string | null;
  start: number;
  end: number;
  speed: number;
  volume: number;
  audio_fade_in: number;
  audio_fade_out: number;
  /** Ken Burns: the framing animates from `crop` to this. */
  crop_to: Crop | null;
}

export interface FreezeSegment extends SegmentBase {
  kind: "freeze";
  media: string | null;
  at: number;
  duration: number;
}

export interface ImageSegment extends SegmentBase {
  kind: "image";
  image: string;
  duration: number;
  crop_to: Crop | null;
}

export type Segment = VideoSegment | FreezeSegment | ImageSegment;

/** Free-positioned text on the clip's output timeline. */
export interface Overlay {
  id: string;
  text: string;
  start: number;
  end: number;
  /** Centre of the text as fractions of the frame. */
  x: number;
  y: number;
  style: OverlayStyle;
}

export interface BrollItem {
  id: string;
  media: string | null;
  image: string | null;
  start: number;
  duration: number;
  media_start: number;
  layout: BrollLayout;
  x: number;
  y: number;
  size: number;
  volume: number;
  fade: number;
}

export interface Marker {
  id: string;
  time: number;
  label: string;
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
  enabled: boolean;
  /** Source span the tracker analysed. */
  span: Span;
  /** Sorted by start; the first starts at `span.start`. */
  shots: Shot[];
}

export interface Edl {
  version: 2;
  aspect: AspectRatio;
  crop: Crop;
  split_screen: boolean;
  tracking: Tracking | null;
  segments: Segment[];
  captions: { words: Word[]; style: CaptionStyle };
  overlays: Overlay[];
  broll: BrollItem[];
  markers: Marker[];
  music: Music | null;
  fade_in: number;
  fade_out: number;
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
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
  created_at: string;
  updated_at: string;
  edl: Edl;
}

/** Mirrors backend `EditCommand` (domain/models/edit_command.py); GET
 * /api/edit-commands/schema has the full schema. */
export type EditCommand =
  | { op: "split"; at: number }
  | { op: "trim"; segment_id: string; start?: number; end?: number; duration?: number }
  | { op: "delete"; segment_ids: string[] }
  | { op: "move"; segment_id: string; to_index: number }
  | { op: "duplicate"; segment_id: string; to_index?: number | null }
  | { op: "insert"; start: number; end: number; media?: string | null; at_index?: number | null }
  | { op: "insert_image"; image: string; duration?: number; at_index?: number | null }
  | { op: "freeze_frame"; at: number; duration?: number }
  | {
      op: "update_segment";
      segment_ids: string[];
      speed?: number;
      volume?: number;
      audio_fade_in?: number;
      audio_fade_out?: number;
      color?: Color;
      color_preset?: ColorPreset;
      crop?: Crop;
      crop_to?: Crop;
      clear_crop?: boolean;
    }
  | { op: "set_transition"; segment_id: string; type?: TransitionType; duration?: number }
  | { op: "remove_transition"; segment_id: string }
  | {
      op: "update_clip";
      aspect?: AspectRatio;
      crop?: Crop;
      split_screen?: boolean;
      tracking_enabled?: boolean;
      fade_in?: number;
      fade_out?: number;
      caption_style?: CaptionStyle;
    }
  | { op: "set_music"; file: string; volume?: number; duck?: boolean }
  | { op: "remove_music" }
  | { op: "edit_words"; words: { index: number; text: string }[] }
  | { op: "delete_words"; indices: number[] }
  | { op: "restore_words"; start?: number; end?: number }
  | { op: "add_overlay"; text: string; start: number; end: number; x?: number; y?: number; style?: OverlayStyle }
  | ({ op: "update_overlay"; id: string } & Partial<Omit<Overlay, "id">>)
  | { op: "remove_overlay"; id: string }
  | ({ op: "add_broll"; start: number; duration: number } & Partial<Omit<BrollItem, "id" | "start" | "duration">>)
  | ({ op: "update_broll"; id: string } & Partial<Omit<BrollItem, "id" | "media" | "image">>)
  | { op: "remove_broll"; id: string }
  | { op: "add_marker"; time: number; label?: string }
  | { op: "remove_marker"; id: string }
  | { op: "reframe_shot"; index: number; x: number; y: number };

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

export interface ImageAsset {
  file: string;
  name: string;
}
