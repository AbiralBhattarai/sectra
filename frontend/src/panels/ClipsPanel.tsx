import { useEffect, useState } from "react";
import { findClipsAgain, listClips } from "../api/client";
import type { Clip, Video } from "../api/types";
import { useEditor } from "../editor/store";
import { formatDuration } from "./SourcesPanel";
import { useClipDownloads } from "./useClipDownloads";

interface Props {
  video: Video | null;
  selectedClipId: string | null;
  onSelect: (clip: Clip) => void;
}

export function ClipsPanel({ video, selectedClipId, onSelect }: Props) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState<string | null>(null);
  // The clip open in the editor changes length as it's edited; reflect saved edits here.
  const saved = useEditor((s) => s.clip);
  const saveState = useEditor((s) => s.saveState);
  const shown = clips.map((c) =>
    c.id === saved?.id ? { ...c, start: saved.start, end: saved.end, updated_at: saved.updated_at } : c,
  );
  const { states: downloads, download } = useClipDownloads();
  const job = video?.current_job;
  // Refetch when the selected video changes or its analysis finishes (again).
  const analysisKey = job?.type === "analyze" ? `${job.id}:${job.status}` : "";

  useEffect(() => {
    if (!video) {
      setClips([]);
      return;
    }
    let cancelled = false;
    listClips(video.id)
      .then((result) => !cancelled && (setClips(result), setError(null)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [video?.id, analysisKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="panel clips">
      <header className="panel-header">
        <h2>Clips{clips.length > 0 && ` · ${clips.length}`}</h2>
        {video?.status === "ready" && (
          <button
            type="button"
            className="small"
            title="Run clip finding again on this video"
            onClick={() => {
              const warning = clips.length
                ? `Find clips again? This replaces all ${clips.length} clips, including your edits.`
                : "Find clips again?";
              if (window.confirm(warning)) {
                findClipsAgain(video.id).catch((e: Error) => setError(e.message));
              }
            }}
          >
            Find clips again
          </button>
        )}
      </header>
      {error && <p className="error">{error}</p>}
      {!video && <p className="placeholder">Select a video to see its clips.</p>}
      {video && clips.length === 0 && !error && (
        <p className="placeholder">{emptyMessage(video)}</p>
      )}
      <ul className="clip-list">
        {shown.map((clip) => (
          <li
            key={clip.id}
            className={`clip-card${clip.id === selectedClipId ? " selected" : ""}`}
            onClick={() => onSelect(clip)}
            title={clip.reason}
          >
            <div className="clip-row">
              <span className="clip-title">{clip.title}</span>
              <span className={`score ${scoreClass(clip.score)}`}>{clip.score}</span>
            </div>
            <p className="clip-hook">{clip.hook}</p>
            <div className="clip-row">
              <span className="stage">
                {formatDuration(clip.start)} · {Math.round(clip.end - clip.start)}s
              </span>
              <DownloadButton
                state={downloads[clip.id]}
                // An open clip with unsaved edits would download the previous version.
                blocked={clip.id === saved?.id && saveState !== "saved"}
                onClick={() => void download(clip)}
              />
            </div>
            {downloads[clip.id]?.status === "rendering" && (
              <progress value={downloads[clip.id].progress} max={1} />
            )}
            {downloads[clip.id]?.status === "failed" && (
              <span className="error">{downloads[clip.id].error}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function emptyMessage(video: Video): string {
  if (video.status === "processing") return "Clips appear once analysis finishes.";
  if (video.status === "failed") return "Processing failed before clips were found.";
  return "The LLM found no clip-worthy moments in this video.";
}

function scoreClass(score: number): string {
  return score >= 75 ? "high" : score >= 50 ? "mid" : "low";
}

interface DownloadButtonProps {
  state: { status: string; progress: number } | undefined;
  blocked: boolean;
  onClick: () => void;
}

function DownloadButton({ state, blocked, onClick }: DownloadButtonProps) {
  const busy = state?.status === "preparing" || state?.status === "rendering";
  const label = busy
    ? state!.status === "rendering"
      ? `Rendering ${Math.round(state!.progress * 100)}%`
      : "Preparing…"
    : blocked
      ? "Saving edits…"
      : "⬇ Download";
  return (
    <button
      type="button"
      className="small"
      disabled={busy || blocked}
      title="Render this clip (if needed) and download the MP4"
      onClick={(event) => {
        event.stopPropagation(); // don't also open the clip
        onClick();
      }}
    >
      {label}
    </button>
  );
}
