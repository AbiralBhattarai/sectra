import { useState, type DragEvent, type FormEvent } from "react";
import { addVideoUrl, deleteVideo, mediaUrl, retryJob, uploadVideo } from "../api/client";
import type { Job, Video } from "../api/types";

interface Props {
  videos: Video[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdded: (video: Video) => void;
  onDeleted: (id: string) => void;
}

interface Upload {
  name: string;
  progress: number;
}

export function SourcesPanel({ videos, selectedId, onSelect, onAdded, onDeleted }: Props) {
  const [urls, setUrls] = useState("");
  const [clipPrompt, setClipPrompt] = useState("");
  const [adding, setAdding] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // One URL per line (or separated by spaces). Added one by one, so they queue in order;
  // lines that fail stay in the box with the reason shown.
  const submitUrls = (event?: FormEvent) => {
    event?.preventDefault();
    const pending = [...new Set(urls.split(/\s+/).map((u) => u.trim()).filter(Boolean))];
    if (!pending.length || adding) return;
    setError(null);
    setAdding(true);
    void (async () => {
      const failed: string[] = [];
      const reasons: string[] = [];
      for (const url of pending) {
        try {
          onAdded(await addVideoUrl(url, clipPrompt));
        } catch (e) {
          failed.push(url);
          reasons.push(`${url}: ${(e as Error).message}`);
        }
      }
      setUrls(failed.join("\n"));
      setError(reasons.length ? reasons.join("\n") : null);
      setAdding(false);
    })();
  };
  const urlCount = new Set(urls.split(/\s+/).filter(Boolean)).size;

  const upload = (files: FileList | null) => {
    for (const file of files ?? []) {
      const setProgress = (progress: number) =>
        setUploads((current) =>
          current.map((u) => (u.name === file.name ? { ...u, progress } : u)),
        );
      setUploads((current) => [...current, { name: file.name, progress: 0 }]);
      void run(async () => {
        try {
          onAdded(await uploadVideo(file, setProgress, clipPrompt));
        } finally {
          setUploads((current) => current.filter((u) => u.name !== file.name));
        }
      });
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files);
  };

  return (
    <section
      className={`panel sources${dragging ? " dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <header className="panel-header">
        <h2>Sources</h2>
        <label className="button">
          Upload
          <input
            type="file"
            accept="video/*,.mkv"
            multiple
            hidden
            onChange={(event) => {
              upload(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
      </header>

      <form className="add-url" onSubmit={submitUrls}>
        <textarea
          rows={Math.min(6, Math.max(1, urls.split("\n").length))}
          placeholder="Paste video URLs, one per line"
          value={urls}
          onChange={(event) => setUrls(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submitUrls();
          }}
          disabled={adding}
        />
        <button type="submit" disabled={adding || urlCount === 0} title="Ctrl/⌘ + Enter">
          {adding ? "Adding…" : urlCount > 1 ? `Add ${urlCount}` : "Add"}
        </button>
      </form>
      <textarea
        className="clip-prompt"
        rows={2}
        maxLength={1000}
        placeholder="What kind of clips? (optional, e.g. funny fails)"
        title="Added to the clip finder's prompt for the videos you add. Empty = find the most viral moments."
        value={clipPrompt}
        onChange={(event) => setClipPrompt(event.target.value)}
        aria-label="What kind of clips to find"
      />
      {error && <p className="error">{error}</p>}

      <ul className="video-list">
        {uploads.map((u) => (
          <li key={`upload-${u.name}`} className="video-card">
            <div className="thumb" />
            <div className="video-meta">
              <span className="video-title">{u.name}</span>
              <span className="stage">Uploading</span>
              <progress value={u.progress} max={1} />
            </div>
          </li>
        ))}
        {videos.map((video) => (
          <VideoCard
            key={video.id}
            video={video}
            selected={video.id === selectedId}
            onSelect={() => onSelect(video.id)}
            onRetry={(job) => void run(() => retryJob(job.id).then(() => undefined))}
            onDelete={() => {
              if (!window.confirm(`Delete "${video.title}" and all its files?`)) return;
              void run(async () => {
                await deleteVideo(video.id);
                onDeleted(video.id);
              });
            }}
          />
        ))}
      </ul>
      {videos.length === 0 && uploads.length === 0 && (
        <p className="placeholder">Add a URL or drop video files here.</p>
      )}
    </section>
  );
}

interface CardProps {
  video: Video;
  selected: boolean;
  onSelect: () => void;
  onRetry: (job: Job) => void;
  onDelete: () => void;
  /** Overrides of the stage names (stories call ANALYZE "split into parts"). */
  stageNames?: Record<string, string>;
}

export function VideoCard({ video, selected, onSelect, onRetry, onDelete, stageNames }: CardProps) {
  const job = video.current_job;
  const names = { ...STAGE_NAMES, ...stageNames };
  return (
    <li
      className={`video-card${selected ? " selected" : ""}`}
      onClick={onSelect}
      title={video.source_url ?? video.title}
    >
      {video.status === "ready" ? (
        <img className="thumb" src={mediaUrl(video.id, "thumbnail.jpg")} alt="" />
      ) : (
        <div className="thumb" />
      )}
      <div className="video-meta">
        <span className="video-title">{video.title}</span>
        {video.status === "ready" && (
          <span className="stage">
            {formatDuration(video.duration)} · {video.width}×{video.height}
          </span>
        )}
        {video.status === "processing" && job && (
          <>
            <span className="stage">{stageLabel(job, names)}</span>
            <progress value={job.progress} max={1} />
          </>
        )}
        {video.status === "failed" && job && (
          <>
            <span className="error">{job.error ?? "Failed"}</span>
            <button
              type="button"
              className="small"
              onClick={(event) => {
                event.stopPropagation();
                onRetry(job);
              }}
            >
              Retry {names[job.type] ?? job.type}
            </button>
          </>
        )}
      </div>
      <button
        type="button"
        className="icon"
        aria-label="Delete video"
        onClick={(event) => {
          event.stopPropagation();
          onDelete();
        }}
      >
        ×
      </button>
    </li>
  );
}

const STAGE_NAMES: Record<string, string> = {
  ingest: "download",
  normalize: "normalize",
  prepare: "prepare",
  vad: "detect speech",
  transcribe: "transcribe",
  analyze: "find clips",
  export: "export",
  narrate: "narrate",
  compose: "build the video",
};

function stageLabel(job: Job, names: Record<string, string>): string {
  const name = names[job.type] ?? job.type;
  const label = name[0].toUpperCase() + name.slice(1);
  return job.status === "queued" ? `Waiting to ${name}` : `${label} · ${Math.round(job.progress * 100)}%`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
