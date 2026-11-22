import { useEffect, useState, type FormEvent } from "react";
import { characterUrl, createStory, deleteVideo, getStoryOptions, retryJob } from "../api/client";
import type { Background, BackgroundMode, NewStory, StoryOptions, Video } from "../api/types";
import { BackgroundsSection } from "./BackgroundsSection";
import { VideoCard } from "./SourcesPanel";

interface Props {
  videos: Video[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdded: (video: Video) => void;
  onDeleted: (id: string) => void;
}

const STORY_STAGES = { analyze: "split into parts" };
/** Narration pace used for the length estimate. */
const WORDS_PER_MINUTE = 160;
const SETTINGS_KEY = "sectra.narrator.settings";

/** How the gameplay background is chosen: black screen, random, random from a
 * category, or one specific clip. */
type BackgroundChoice = "black" | "random" | `category:${string}` | `clip:${string}`;

interface Settings {
  polish: boolean;
  character: string | null;
  voice: string;
  speed: number;
  background: BackgroundChoice;
}

const DEFAULTS: Settings = { polish: true, character: "guy", voice: "am_michael", speed: 1, background: "black" };

function loadSettings(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") };
  } catch {
    return DEFAULTS;
  }
}

function saveSettings(settings: Settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // private mode etc.: settings just aren't remembered
  }
}

export function NarratorPanel({ videos, selectedId, onSelect, onAdded, onDeleted }: Props) {
  const [options, setOptions] = useState<StoryOptions | null>(null);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backgrounds, setBackgrounds] = useState<Background[]>([]);

  useEffect(() => {
    getStoryOptions().then(setOptions, (e: Error) => setError(e.message));
  }, []);

  const change = (patch: Partial<Settings>) =>
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveSettings(next);
      return next;
    });

  const pickCharacter = (character: string | null) => {
    const voice = options?.characters.find((c) => c.id === character)?.voice;
    change({ character, ...(voice ? { voice } : {}) });
  };

  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const minutes = words / WORDS_PER_MINUTE / settings.speed;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || creating) return;
    setError(null);
    setCreating(true);
    createStory(toRequest(title, text, settings))
      .then((video) => {
        onAdded(video);
        onSelect(video.id);
        setText("");
        setTitle("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setCreating(false));
  };

  const categories = [...new Set(backgrounds.map((b) => b.category))];
  const run = (action: () => Promise<unknown>) => action().catch((e: Error) => setError(e.message));

  return (
    <section className="panel sources narrator">
      <header className="panel-header">
        <h2>Narrator</h2>
      </header>

      <form className="story-form" onSubmit={submit}>
        <input
          type="text"
          placeholder="Title (optional)"
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          rows={8}
          placeholder="Paste a story to narrate…"
          maxLength={20000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e);
          }}
        />
        <span className="hint">
          {words} words{words > 0 && ` · about ${formatMinutes(minutes)}`}
          {minutes > 2.8 && " · split into parts"}
        </span>

        <label className="checkbox" title="Your local LLM rewrites it for narration (hook first, no Reddit leftovers) and writes the title and caption">
          <input type="checkbox" checked={settings.polish} onChange={(e) => change({ polish: e.target.checked })} />
          Polish with AI
        </label>

        <div className="character-picker" role="radiogroup" aria-label="Narrator character">
          {(options?.characters ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={settings.character === c.id}
              className={`character-choice${settings.character === c.id ? " selected" : ""}`}
              onClick={() => pickCharacter(c.id)}
              title={c.label}
            >
              <img src={characterUrl(c.id, "preview.svg")} alt="" />
              <span>{c.label.split(" (")[0]}</span>
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={settings.character === null}
            className={`character-choice none${settings.character === null ? " selected" : ""}`}
            onClick={() => pickCharacter(null)}
          >
            <span className="no-character">∅</span>
            <span>None</span>
          </button>
        </div>

        <label className="field">
          Voice
          <select value={settings.voice} onChange={(e) => change({ voice: e.target.value })}>
            {(options?.voices ?? []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Speed {settings.speed.toFixed(2)}×
          <input
            type="range"
            min={0.8}
            max={1.3}
            step={0.05}
            value={settings.speed}
            onChange={(e) => change({ speed: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          Background
          <select
            value={settings.background}
            onChange={(e) => change({ background: e.target.value as BackgroundChoice })}
          >
            <option value="black">Black screen</option>
            <option value="random" disabled={backgrounds.length === 0}>
              Random gameplay
            </option>
            {categories.map((category) => (
              <option key={category} value={`category:${category}`}>
                Random · {category}
              </option>
            ))}
            {backgrounds.map((b) => (
              <option key={b.ref} value={`clip:${b.ref}`}>
                {b.category} · {b.name}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" disabled={!text.trim() || creating || !options} title="Ctrl/⌘ + Enter">
          {creating ? "Starting…" : "Narrate"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      <BackgroundsSection onChange={setBackgrounds} />

      <h3 className="subhead">Stories</h3>
      <ul className="video-list">
        {videos.map((video) => (
          <VideoCard
            key={video.id}
            video={video}
            selected={video.id === selectedId}
            onSelect={() => onSelect(video.id)}
            stageNames={STORY_STAGES}
            onRetry={(job) => run(() => retryJob(job.id))}
            onDelete={() => {
              if (!window.confirm(`Delete "${video.title}" and all its files?`)) return;
              run(async () => {
                await deleteVideo(video.id);
                onDeleted(video.id);
              });
            }}
          />
        ))}
      </ul>
      {videos.length === 0 && <p className="placeholder">Paste a story above to make your first narration.</p>}
    </section>
  );
}

function toRequest(title: string, text: string, settings: Settings): NewStory {
  const choice = settings.background;
  const mode: BackgroundMode = choice === "black" ? "black" : "gameplay";
  return {
    title: title.trim(),
    text,
    polish: settings.polish,
    voice: settings.voice,
    speed: settings.speed,
    character: settings.character,
    background_mode: mode,
    background: choice.startsWith("clip:") ? choice.slice(5) : null,
    category: choice.startsWith("category:") ? choice.slice(9) : null,
  };
}

function formatMinutes(minutes: number): string {
  const seconds = Math.round(minutes * 60);
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
