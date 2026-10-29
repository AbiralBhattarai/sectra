import { useEffect, useRef } from "react";
import { musicUrl } from "../api/client";
import { sourceToOutput } from "./edlOps";
import { useEditor } from "./store";

/** Preview gain while someone speaks, approximating the render's sidechain ducking. */
const DUCKED = 0.35;
/** Resync when the track drifts further than this from the clip's output time. */
const MAX_DRIFT = 0.25;

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
      const speaking = speech.some((s) => playhead >= s.start && playhead < s.end);
      audio.volume = music.volume * (music.duck && speaking ? DUCKED : 1);
      const expected = audio.duration ? sourceToOutput(playhead, edl.ranges) % audio.duration : 0;
      if (Math.abs(audio.currentTime - expected) > MAX_DRIFT) audio.currentTime = expected;
      if (audio.paused) void audio.play().catch(() => undefined);
    };
    sync();
    return useEditor.subscribe(sync);
  }, [music]);

  return music ? <audio ref={audioRef} src={musicUrl(music.file)} loop preload="auto" /> : null;
}
