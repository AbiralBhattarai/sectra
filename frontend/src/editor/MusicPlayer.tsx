import { useEffect, useRef } from "react";
import { musicUrl } from "../api/client";
import { clipFade } from "./player/playback";
import { isClipVideo, layout, mediaTime, placedAt } from "./sequence";
import { useEditor } from "./store";

/** Preview gain while someone speaks, approximating the render's sidechain ducking. */
const DUCKED = 0.35;
/** Resync when the track drifts further than this from the clip's output time. */
const MAX_DRIFT = 0.75;

/** Plays the background track in step with the preview: music time = clip output time,
 * looping like the render does. */
export function MusicPlayer() {
  const music = useEditor((s) => s.edl?.music ?? null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !music) return;
    const sync = () => {
      const { playhead, playing, edl, speech } = useEditor.getState();
      if (!edl) return;
      if (!playing) {
        if (!audio.paused) audio.pause();
        return;
      }
      // Speech (VAD) is on the clip video's timeline.
      const placed = layout(edl.segments);
      const owner = placedAt(placed, playhead);
      const source = owner && isClipVideo(owner.segment) ? mediaTime(owner, playhead) : null;
      const speaking = source != null && speech.some((s) => source >= s.start && source < s.end);
      const duration = placed.length ? placed[placed.length - 1].end : 0;
      audio.volume = music.volume * (music.duck && speaking ? DUCKED : 1) * clipFade(edl, playhead, duration);
      const expected = audio.duration ? playhead % audio.duration : 0;
      if (!audio.seeking && Math.abs(audio.currentTime - expected) > MAX_DRIFT) audio.currentTime = expected;
      if (audio.paused) void audio.play().catch(() => undefined);
    };
    sync();
    return useEditor.subscribe(sync);
  }, [music]);

  return music ? <audio ref={audioRef} src={musicUrl(music.file)} loop preload="auto" /> : null;
}
