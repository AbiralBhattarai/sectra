import { useEffect, useState } from "react";
import { getStoryOptions } from "../api/client";
import type { StoryOptions } from "../api/types";
import { clamp, sourceToOutput } from "./edlOps";
import { clock } from "./Preview";
import { useEditor } from "./store";
import { EMOTIONS, type CharacterTrack, type Emotion, type Mood } from "./types";

/** Gap between the character's head and the bottom of the captions (frame height). */
const CAPTION_GAP = 0.03;
const NEW_MOOD_SECONDS = 3;

/** Narrator tab: show/hide, swap, resize the character and edit its expressions. */
export function CharacterEditor() {
  const edl = useEditor((s) => s.edl)!;
  const playhead = useEditor((s) => s.playhead);
  const { edit, seek } = useEditor.getState();
  const [options, setOptions] = useState<StoryOptions | null>(null);
  const [draftScale, setDraftScale] = useState<number | null>(null);
  const track = edl.character!;

  useEffect(() => {
    getStoryOptions().then(setOptions, () => setOptions(null));
  }, []);

  const update = (patch: Partial<CharacterTrack>) =>
    edit((e) => (e.character ? { ...e, character: { ...e.character, ...patch } } : e));
  const setMoods = (moods: Mood[]) => update({ moods: [...moods].sort((a, b) => a.start - b.start) });
  const captionsAbove = () =>
    edit((e) => {
      const c = e.character!;
      const y = Math.round(clamp(c.y - c.scale / 2 - CAPTION_GAP, 0.1, 1) * 1000) / 1000;
      return { ...e, captions: { ...e.captions, y } };
    });

  const addMood = () => {
    const start = Math.round(playhead * 100) / 100;
    const next = track.moods.find((m) => m.start > start);
    const end = Math.min(start + NEW_MOOD_SECONDS, next?.start ?? Infinity, edl.ranges[edl.ranges.length - 1].end);
    if (end - start < 0.2 || track.moods.some((m) => m.start <= start && start < m.end)) return;
    setMoods([...track.moods, { start, end, emotion: "happy" }]);
  };

  return (
    <div className="tab-body">
      <label className="checkbox">
        <input type="checkbox" checked={track.enabled} onChange={(e) => update({ enabled: e.target.checked })} />
        Show the narrator
      </label>
      <label className="field">
        Character
        <select value={track.name} onChange={(e) => update({ name: e.target.value })}>
          {(options?.characters ?? [{ id: track.name, label: track.name, voice: "" }]).map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Size
        <input
          type="range"
          min={0.15}
          max={0.8}
          step={0.01}
          value={draftScale ?? track.scale}
          onChange={(e) => setDraftScale(Number(e.target.value))}
          onPointerUp={() => {
            if (draftScale != null) update({ scale: draftScale });
            setDraftScale(null);
          }}
          onKeyUp={() => {
            if (draftScale != null) update({ scale: draftScale });
            setDraftScale(null);
          }}
        />
      </label>
      <p className="hint">Drag the narrator in the preview to move it.</p>
      <button type="button" onClick={captionsAbove}>
        Put captions above the narrator
      </button>

      <h3 className="subhead">Expressions</h3>
      <p className="hint">Picked by the AI from the story; the rest of the time the narrator is neutral.</p>
      <ul className="mood-list">
        {track.moods.map((mood, index) => (
          <li key={`${mood.start}-${index}`}>
            <button type="button" className="small" onClick={() => seek(mood.start)}>
              {clock(sourceToOutput(mood.start, edl.ranges))}
            </button>
            <select
              value={mood.emotion}
              onChange={(e) =>
                setMoods(track.moods.map((m, i) => (i === index ? { ...m, emotion: e.target.value as Emotion } : m)))
              }
            >
              {EMOTIONS.filter((e) => e !== "neutral").map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
            <span className="stage">{(mood.end - mood.start).toFixed(1)}s</span>
            <button
              type="button"
              className="icon"
              aria-label="Remove expression"
              onClick={() => setMoods(track.moods.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={addMood}>
        + Expression at playhead
      </button>
    </div>
  );
}
