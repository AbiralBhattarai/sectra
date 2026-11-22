import { useEffect, useState } from "react";
import { findClipsAgain, listClips } from "../api/client";
import type { Clip, Video } from "../api/types";
import { useEditor } from "../editor/store";
import { formatDuration } from "./SourcesPanel";
import { platformState, useClipPosting, type PostState } from "./useClipPosting";

interface Props {
  video: Video | null;
  selectedClipId: string | null;
  onSelect: (clip: Clip) => void;
}

export function ClipsPanel({ video, selectedClipId, onSelect }: Props) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState<string | null>(null);
  // "Find clips again" form: the prompt being edited, or null when closed.
  const [refind, setRefind] = useState<string | null>(null);
  // The clip open in the editor changes length as it's edited; reflect saved edits here.
  const saved = useEditor((s) => s.clip);
  const saveState = useEditor((s) => s.saveState);
  const shown = clips.map((c) =>
    c.id === saved?.id ? { ...c, start: saved.start, end: saved.end, updated_at: saved.updated_at } : c,
  );
  const { states: posts, post } = useClipPosting(clips);
  // Post captions being typed, per clip; saved on the clip when it's posted.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const postCaption = (clip: Clip) => drafts[clip.id] ?? clip.post_caption ?? "";
  const postWith = (clip: Clip) => {
    const text = postCaption(clip).trim();
    setClips((current) => current.map((c) => (c.id === clip.id ? { ...c, post_caption: text } : c)));
    void post(clip, text);
  };
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
            onClick={() => setRefind(refind === null ? video.clip_prompt : null)}
          >
            Find clips again
          </button>
        )}
      </header>
      {video && refind !== null && (
        <form
          className="refind"
          onSubmit={(event) => {
            event.preventDefault();
            setRefind(null);
            findClipsAgain(video.id, refind).catch((e: Error) => setError(e.message));
          }}
        >
          <textarea
            rows={2}
            maxLength={1000}
            autoFocus
            placeholder="What kind of clips? Empty = find the most viral moments."
            value={refind}
            onChange={(event) => setRefind(event.target.value)}
          />
          {clips.length > 0 && (
            <p className="hint">This replaces all {clips.length} clips, including your edits.</p>
          )}
          <div className="row">
            <button type="submit">Find clips</button>
            <button type="button" onClick={() => setRefind(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
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
            <input
              className="post-caption"
              type="text"
              maxLength={2000}
              placeholder="Caption after the title, e.g. #lacy"
              title={`Posted as: ${[clip.title, postCaption(clip).trim()].filter(Boolean).join(" ")}`}
              value={postCaption(clip)}
              onClick={(event) => event.stopPropagation()} // don't open the clip
              onKeyDown={(event) => event.stopPropagation()} // editor shortcuts (Space, S…)
              onChange={(event) => setDrafts((d) => ({ ...d, [clip.id]: event.target.value }))}
            />
            <div className="clip-row">
              <span className="stage">
                {formatDuration(clip.start)} · {Math.round(clip.end - clip.start)}s
              </span>
              <PostButton
                state={posts[clip.id]}
                // An open clip with unsaved edits would post the previous version.
                blocked={clip.id === saved?.id && saveState !== "saved"}
                onClick={() => postWith(clip)}
              />
            </div>
            {posts[clip.id]?.phase === "rendering" && <progress value={posts[clip.id].progress} max={1} />}
            {posts[clip.id] && <PostDetails state={posts[clip.id]} />}
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

interface PostButtonProps {
  state: PostState | undefined;
  blocked: boolean;
  onClick: () => void;
}

const PLATFORM_NAMES: Record<string, string> = {
  youtube: "YouTube",
  tiktok: "TikTok",
  instagram: "Instagram",
  x: "X",
  facebook: "Facebook",
};

function PostButton({ state, blocked, onClick }: PostButtonProps) {
  const phase = state?.phase;
  const busy = phase === "starting" || phase === "rendering" || phase === "posting";
  const label =
    phase === "starting"
      ? "Starting…"
      : phase === "rendering"
        ? `Rendering ${Math.round(state!.progress * 100)}%`
        : phase === "posting"
          ? "Posting…"
          : blocked
            ? "Saving edits…"
            : phase === "done" || phase === "failed"
              ? "↻ Post again"
              : "➤ Post";
  return (
    <button
      type="button"
      className="small"
      disabled={busy || blocked}
      title="Render this clip and post it (title + caption as the description) to every platform — needs `make poster` running"
      onClick={(event) => {
        event.stopPropagation(); // don't also open the clip
        onClick();
      }}
    >
      {label}
    </button>
  );
}

/** One chip per platform: posted (links to the post), failed, needs login, or waiting. */
function PostDetails({ state }: { state: PostState }) {
  if (state.phase === "failed") return <span className="error">{state.error}</span>;
  const status = state.status;
  if (!status || state.phase === "starting" || state.phase === "rendering") return null;
  return (
    <div className="post-platforms" onClick={(event) => event.stopPropagation()}>
      {!status.in_outbox && <span className="hint">Waiting for the outbox…</span>}
      {status.in_outbox &&
        status.platforms.map((platform) => {
          const name = PLATFORM_NAMES[platform] ?? platform;
          const at = platformState(status, platform);
          if (at === "posted") {
            const url = status.posted[platform].url;
            return url ? (
              <a key={platform} className="chip posted" href={url} target="_blank" rel="noreferrer">
                ✓ {name}
              </a>
            ) : (
              <span key={platform} className="chip posted">
                ✓ {name}
              </span>
            );
          }
          const title =
            at === "failed"
              ? status.failures[platform]?.error
              : at === "blocked"
                ? status.blocked[platform].reason
                : status.failures[platform]
                  ? `Retrying (${status.failures[platform].count} failed): ${status.failures[platform].error ?? ""}`
                  : "Waiting for the poster (is `make poster` running?)";
          const mark = at === "failed" ? "✗" : at === "blocked" ? "🔒" : "…";
          return (
            <span key={platform} className={`chip ${at}`} title={title}>
              {mark} {name}
            </span>
          );
        })}
    </div>
  );
}
