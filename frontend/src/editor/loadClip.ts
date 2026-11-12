import { getClip, getMediaJson, listVideos } from "../api/client";
import type { Video } from "../api/types";
import { useEditor, type EditorAssets } from "./store";
import type { Peaks, SpeechMap, Transcript } from "./types";

const assetCache = new Map<string, Promise<EditorAssets>>();

/** Transcript words, VAD speech and waveform for a video; fetched once per video. */
function videoAssets(videoId: string): Promise<EditorAssets> {
  let assets = assetCache.get(videoId);
  if (!assets) {
    assets = Promise.all([
      getMediaJson<Transcript>(videoId, "transcript.json"),
      getMediaJson<SpeechMap>(videoId, "speech.json"),
      getMediaJson<Peaks>(videoId, "peaks.json").catch(() => null),
    ]).then(([transcript, speech, peaks]) => ({
      transcript: transcript.segments.flatMap((s) => s.words),
      speech: speech.segments,
      peaks,
    }));
    assets.catch(() => assetCache.delete(videoId));
    assetCache.set(videoId, assets);
  }
  return assets;
}

export async function loadClip(clipId: string, video: Video) {
  const [clip, assets] = await Promise.all([getClip(clipId), videoAssets(video.id)]);
  return { clip, assets };
}

/** Sizes of every video in the library, for framing segments and B-roll that use them. */
export async function loadMediaSizes(): Promise<void> {
  const videos = await listVideos();
  const { noteMediaSize } = useEditor.getState();
  for (const v of videos) if (v.width && v.height) noteMediaSize(v.id, { width: v.width, height: v.height });
}
