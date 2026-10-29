import { useEffect, useMemo, useRef, useState } from "react";
import { listMusic, musicUrl, uploadMusic } from "../api/client";
import { useEditor } from "./store";
import type { MusicTrack } from "./types";

const DEFAULT_VOLUME = 0.15;

export function MusicEditor() {
  const music = useEditor((s) => s.edl!.music);
  const { edit } = useEditor.getState();
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  // Volume while the slider is held; committed as one undo step on release.
  const [draftVolume, setDraftVolume] = useState<number | null>(null);

  // Plays the chosen track on its own, to audition it without playing the clip.
  const auditionRef = useRef<HTMLAudioElement>(null);
  const [auditioning, setAuditioning] = useState(false);

  useEffect(() => {
    listMusic().then(setTracks, (e: Error) => setError(e.message));
  }, []);

  const groups = useMemo(() => groupTracks(tracks), [tracks]);

  const toggleAudition = () => {
    const audio = auditionRef.current;
    if (!audio || !music) return;
    if (auditioning) {
      audio.pause();
      setAuditioning(false);
    } else {
      audio.currentTime = 0;
      audio.volume = 0.6;
      void audio.play().then(() => setAuditioning(true), () => setAuditioning(false));
    }
  };

  const choose = (file: string) =>
    edit((e) => ({
      ...e,
      music: file ? { file, volume: e.music?.volume ?? DEFAULT_VOLUME, duck: e.music?.duck ?? true } : null,
    }));

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const track = await uploadMusic(file);
      setTracks((current) => [...current, track].sort((a, b) => a.file.localeCompare(b.file)));
      choose(track.file);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const commitVolume = () => {
    if (draftVolume != null) edit((e) => (e.music ? { ...e, music: { ...e.music, volume: draftVolume } } : e));
    setDraftVolume(null);
  };

  return (
    <div className="tab-body">
      <label className="field">
        Background track ({tracks.length} available)
        <span className="track-picker">
          <select
            value={music?.file ?? ""}
            onChange={(event) => {
              auditionRef.current?.pause();
              setAuditioning(false);
              choose(event.target.value);
            }}
          >
            <option value="">None</option>
            {groups.map(([label, items]) => (
              <optgroup key={label} label={label}>
                {items.map((track) => (
                  <option key={track.file} value={track.file}>
                    {track.artist ? `${track.name} — ${track.artist}` : track.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            type="button"
            className="small"
            disabled={!music}
            onClick={toggleAudition}
            aria-label={auditioning ? "Stop preview" : "Preview track"}
            title="Listen to the track on its own"
          >
            {auditioning ? "■" : "▶"}
          </button>
        </span>
        {music && (
          <audio
            ref={auditionRef}
            src={musicUrl(music.file)}
            preload="none"
            onEnded={() => setAuditioning(false)}
          />
        )}
      </label>
      <label className="button">
        {uploading ? "Uploading…" : "Upload track"}
        <input
          type="file"
          accept="audio/*"
          hidden
          disabled={uploading}
          onChange={(event) => {
            void upload(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </label>
      {error && <p className="error">{error}</p>}
      {music && (
        <>
          <label className="field">
            Volume {Math.round((draftVolume ?? music.volume) * 100)}%
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={draftVolume ?? music.volume}
              onChange={(event) => setDraftVolume(Number(event.target.value))}
              onPointerUp={commitVolume}
              onKeyUp={commitVolume}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={music.duck}
              onChange={(event) =>
                edit((e) => (e.music ? { ...e, music: { ...e.music, duck: event.target.checked } } : e))
              }
            />
            Lower the music while someone speaks
          </label>
          <p className="stage">The track starts with the clip and loops if it's shorter.</p>
        </>
      )}
    </div>
  );
}

/** Built-in tracks grouped by mood (alphabetically), then the user's uploads. */
function groupTracks(tracks: MusicTrack[]): [string, MusicTrack[]][] {
  const byMood = new Map<string, MusicTrack[]>();
  for (const track of tracks.filter((t) => t.default)) {
    const mood = track.mood ?? "other";
    byMood.set(mood, [...(byMood.get(mood) ?? []), track]);
  }
  const groups: [string, MusicTrack[]][] = [...byMood.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([mood, items]) => [capitalise(mood), [...items].sort((a, b) => a.name.localeCompare(b.name))]);
  const uploads = tracks.filter((t) => !t.default);
  if (uploads.length) groups.push(["Your uploads", uploads]);
  return groups;
}

function capitalise(text: string): string {
  return text === "lofi" ? "Lo-fi" : text === "hiphop" ? "Hip-hop" : text[0].toUpperCase() + text.slice(1);
}
