import { useCallback, useEffect, useState, type FormEvent } from "react";
import { addBackgroundUrl, backgroundUrl, deleteBackground, listBackgrounds, retryJob, uploadBackground } from "../api/client";
import type { Background, BackgroundLibrary, JobEvent } from "../api/types";
import { useJobEvents } from "../api/useJobEvents";

interface Props {
  /** Called with the finished clips whenever the library changes. */
  onChange: (ready: Background[]) => void;
}

const OPEN_KEY = "sectra.narrator.backgroundsOpen";

/** The gameplay library stories can use as a background: add by URL or upload, tagged
 * with a category (minecraft, subway-surfers, …). */
export function BackgroundsSection({ onChange }: Props) {
  const [library, setLibrary] = useState<BackgroundLibrary>({ ready: [], pending: [] });
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(OPEN_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState("");
  const [uploads, setUploads] = useState<{ name: string; progress: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await listBackgrounds();
      setLibrary(next);
      onChange(next.ready);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [onChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useJobEvents((event: JobEvent) => {
    if (event.type !== "background") return;
    if (event.status === "succeeded" || event.status === "failed" || event.status === "queued") {
      void refresh();
      return;
    }
    setLibrary((current) => ({
      ...current,
      pending: current.pending.map((p) =>
        p.job_id === event.job_id ? { ...p, status: event.status, progress: event.progress } : p,
      ),
    }));
  });

  const toggle = () => {
    setOpen(!open);
    try {
      localStorage.setItem(OPEN_KEY, open ? "0" : "1");
    } catch {
      // not remembered
    }
  };

  const cleanCategory = category.trim().toLowerCase().replace(/\s+/g, "-");
  const addUrl = (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim() || !cleanCategory) return;
    setError(null);
    addBackgroundUrl(url.trim(), cleanCategory)
      .then(() => {
        setUrl("");
        return refresh();
      })
      .catch((e: Error) => setError(e.message));
  };

  const upload = (files: FileList | null) => {
    if (!cleanCategory) {
      setError("Type a category first (e.g. minecraft)");
      return;
    }
    for (const file of files ?? []) {
      setUploads((current) => [...current, { name: file.name, progress: 0 }]);
      uploadBackground(file, cleanCategory, (progress) =>
        setUploads((current) => current.map((u) => (u.name === file.name ? { ...u, progress } : u))),
      )
        .then(refresh)
        .catch((e: Error) => setError(e.message))
        .finally(() => setUploads((current) => current.filter((u) => u.name !== file.name)));
    }
  };

  const categories = [...new Set(library.ready.map((b) => b.category))];
  const busy = library.pending.filter((p) => p.status !== "failed").length + uploads.length;

  return (
    <div className="backgrounds">
      <button type="button" className="section-toggle" onClick={toggle} aria-expanded={open}>
        {open ? "▾" : "▸"} Gameplay backgrounds · {library.ready.length}
        {busy > 0 && ` (+${busy} adding)`}
      </button>
      {open && (
        <>
          <form className="add-background" onSubmit={addUrl}>
            <input
              type="text"
              list="background-categories"
              placeholder="Category, e.g. minecraft"
              value={category}
              maxLength={40}
              onChange={(e) => setCategory(e.target.value)}
            />
            <datalist id="background-categories">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <div className="row">
              <input
                type="url"
                placeholder="Gameplay video URL"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <button type="submit" disabled={!url.trim() || !cleanCategory}>
                Add
              </button>
              <label className="button" title="Upload gameplay files into this category">
                Upload
                <input
                  type="file"
                  accept="video/*,.mkv"
                  multiple
                  hidden
                  onChange={(e) => {
                    upload(e.target.files);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
          </form>
          {error && <p className="error">{error}</p>}
          <p className="hint">
            Use footage you're allowed to repost. Audio is removed; each story starts at a random point.
          </p>
          <ul className="background-list">
            {uploads.map((u) => (
              <li key={`upload-${u.name}`}>
                <span className="stage">Uploading {u.name}</span>
                <progress value={u.progress} max={1} />
              </li>
            ))}
            {library.pending.map((p) => (
              <li key={p.job_id}>
                <span className="stage" title={p.source}>
                  {p.category} · {p.status === "failed" ? "failed" : p.status === "queued" ? "waiting…" : "adding"}
                </span>
                {p.status === "running" && <progress value={p.progress} max={1} />}
                {p.status === "failed" && (
                  <>
                    <span className="error">{p.error}</span>
                    <button
                      type="button"
                      className="small"
                      onClick={() => retryJob(p.job_id).then(refresh, (e: Error) => setError(e.message))}
                    >
                      Retry
                    </button>
                  </>
                )}
              </li>
            ))}
            {library.ready.map((b) => (
              <li key={b.ref} className="background-item">
                <video
                  src={backgroundUrl(b.ref)}
                  muted
                  preload="metadata"
                  onMouseEnter={(e) => void e.currentTarget.play().catch(() => undefined)}
                  onMouseLeave={(e) => e.currentTarget.pause()}
                />
                <span className="video-title" title={b.name}>
                  <span className="chip">{b.category}</span> {b.name}
                </span>
                <button
                  type="button"
                  className="icon"
                  aria-label={`Delete ${b.name}`}
                  onClick={() => {
                    if (!window.confirm(`Delete "${b.name}" from the library?`)) return;
                    deleteBackground(b.ref).then(refresh, (e: Error) => setError(e.message));
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
