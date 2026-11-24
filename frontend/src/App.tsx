import { useState } from "react";
import { mediaUrl } from "./api/client";
import type { Clip, VideoKind } from "./api/types";
import { useVideos } from "./api/useVideos";
import { Editor } from "./editor/Editor";
import { ErrorBoundary } from "./ErrorBoundary";
import { ClipsPanel } from "./panels/ClipsPanel";
import { NarratorPanel } from "./panels/NarratorPanel";
import { SourcesPanel } from "./panels/SourcesPanel";
import { Timeline } from "./timeline/Timeline";

type Mode = "clipper" | "narrator";

const MODES: { id: Mode; label: string; kind: VideoKind; hint: string }[] = [
  { id: "clipper", label: "Clipper", kind: "source", hint: "Long videos → highlight clips" },
  { id: "narrator", label: "Narrator", kind: "story", hint: "Stories → narrated, captioned videos" },
];
const MODE_KEY = "sectra.mode";

function initialMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === "narrator" ? "narrator" : "clipper";
  } catch {
    return "clipper";
  }
}

export function App() {
  const { videos, error, upsert, remove } = useVideos();
  const [mode, setMode] = useState<Mode>(initialMode);
  // Each tab remembers its own selection.
  const [selectedIds, setSelectedIds] = useState<Record<Mode, string | null>>({ clipper: null, narrator: null });
  const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
  const kind = MODES.find((m) => m.id === mode)!.kind;
  const shown = videos.filter((v) => (v.kind ?? "source") === kind);
  const selectedId = selectedIds[mode];
  const selected = shown.find((v) => v.id === selectedId) ?? null;
  const clip = selectedClip?.video_id === selectedId ? selectedClip : null;

  const selectVideo = (id: string | null) => {
    setSelectedIds((current) => ({ ...current, [mode]: id }));
    setSelectedClip(null);
  };
  const switchMode = (next: Mode) => {
    setMode(next);
    setSelectedClip(null);
    try {
      localStorage.setItem(MODE_KEY, next);
    } catch {
      // not remembered
    }
  };
  const onDeleted = (id: string) => {
    remove(id);
    if (id === selectedId) selectVideo(null);
  };

  return (
    <div className="app">
      <nav className="mode-tabs" role="tablist" aria-label="Feature">
        <span className="brand">Sectra</span>
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            className={mode === m.id ? "active" : undefined}
            title={m.hint}
            onClick={() => switchMode(m.id)}
          >
            {m.label}
            <span className="count">{videos.filter((v) => (v.kind ?? "source") === m.kind).length}</span>
          </button>
        ))}
      </nav>
      {mode === "clipper" ? (
        <SourcesPanel
          videos={shown}
          selectedId={selectedId}
          onSelect={selectVideo}
          onAdded={upsert}
          onDeleted={onDeleted}
        />
      ) : (
        <NarratorPanel
          videos={shown}
          selectedId={selectedId}
          onSelect={selectVideo}
          onAdded={upsert}
          onDeleted={onDeleted}
        />
      )}
      <main className="panel editor">
        {error && <p className="error">{error}</p>}
        {clip && selected ? (
          <ErrorBoundary key={clip.id} label="Editor">
            <Editor clipId={clip.id} video={selected} />
          </ErrorBoundary>
        ) : (
          <>
            <h2>Editor</h2>
            {/* width is set once normalization has written source.mp4 — minutes into a
                long pipeline — so the video is watchable long before clips exist. */}
            {selected && selected.width != null ? (
              <>
                <video
                  key={selected.id}
                  className="preview"
                  src={mediaUrl(selected.id, "source.mp4")}
                  controls
                  preload="metadata"
                />
                {selected.status === "processing" && (
                  <p className="stage">
                    {mode === "narrator"
                      ? "Still captioning — the parts will appear on the right when ready."
                      : "Still processing — clips will appear on the right when ready."}
                  </p>
                )}
              </>
            ) : (
              <p className="placeholder">{placeholder(mode, selected != null)}</p>
            )}
          </>
        )}
      </main>
      <ClipsPanel video={selected} selectedClipId={clip?.id ?? null} onSelect={setSelectedClip} />
      {clip ? (
        <ErrorBoundary key={clip.id} label="Timeline">
          <Timeline />
        </ErrorBoundary>
      ) : (
        <section className="panel timeline">
          <h2>Timeline</h2>
        </section>
      )}
    </div>
  );
}

function placeholder(mode: Mode, selected: boolean): string {
  if (mode === "narrator") {
    return selected
      ? "Narrating — the video will play here once the voice-over is built."
      : "Paste a story on the left, then pick a part to edit it here.";
  }
  return selected
    ? "Downloading — the video will play here in a few minutes."
    : "Select a video, then a clip to edit it here.";
}
