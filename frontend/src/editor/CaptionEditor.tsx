import { useEffect, useMemo, useState } from "react";
import { paginate } from "./captions";
import { clamp, sourceToOutput } from "./edlOps";
import { clock } from "./Preview";
import { useEditor } from "./store";
import type { CaptionStyle, Word } from "./types";

const STYLES: { value: CaptionStyle; label: string }[] = [
  { value: "bold-highlight", label: "Bold highlight" },
  { value: "clean", label: "Clean" },
  { value: "boxed", label: "Boxed" },
  { value: "none", label: "No captions" },
];

export function CaptionEditor() {
  const edl = useEditor((s) => s.edl)!;
  const selected = useEditor((s) => s.selectedWord);
  const { edit, selectWord, seek } = useEditor.getState();
  const words = edl.captions.words;
  // Pages are listed in the style's grouping, but "none" still lists words to edit.
  const pages = useMemo(
    () => paginate(words, edl.captions.style === "none" ? "clean" : edl.captions.style),
    [words, edl.captions.style],
  );

  const choose = (word: Word) => {
    selectWord(words.indexOf(word));
    seek(word.start);
  };

  return (
    <div className="tab-body">
      <label className="field">
        Caption style
        <select
          value={edl.captions.style}
          onChange={(event) =>
            edit((e) => ({ ...e, captions: { ...e.captions, style: event.target.value as CaptionStyle } }))
          }
        >
          {STYLES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {selected != null && words[selected] && <WordForm index={selected} word={words[selected]} />}

      <ol className="caption-pages">
        {pages.map((page) => (
          <li key={`${page.start}-${page.words[0].text}`}>
            <span className="stage">{clock(sourceToOutput(page.start, edl.ranges))}</span>
            <span>
              {page.words.map((word) => (
                <button
                  type="button"
                  key={`${word.start}-${word.text}`}
                  className={`word${words[selected ?? -1] === word ? " selected" : ""}`}
                  onClick={() => choose(word)}
                >
                  {word.text}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ol>
      {words.length === 0 && <p className="placeholder">No words in this clip.</p>}
    </div>
  );
}

function WordForm({ index, word }: { index: number; word: Word }) {
  const { edit, selectWord } = useEditor.getState();
  const [text, setText] = useState(word.text);
  useEffect(() => setText(word.text), [word]);

  const update = (patch: Partial<Word>) =>
    edit((e) => {
      const next = { ...word, ...patch };
      if (!next.text.trim() || next.end - next.start < 0.02) return e; // ignore invalid input
      const words = e.captions.words.map((w, i) => (i === index ? next : w)).sort((a, b) => a.start - b.start);
      return { ...e, captions: { ...e.captions, words } };
    });
  const nudge = (field: "start" | "end", delta: number) =>
    update({ [field]: Math.round(clamp(word[field] + delta, 0, Infinity) * 100) / 100 });

  return (
    <div className="word-form">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => text !== word.text && update({ text })}
        onKeyDown={(event) => event.key === "Enter" && (event.target as HTMLInputElement).blur()}
        aria-label="Word text"
      />
      {(["start", "end"] as const).map((field) => (
        <div className="nudge" key={field}>
          <span>{field}</span>
          <button type="button" onClick={() => nudge(field, -0.05)}>−</button>
          <span className="timecode">{word[field].toFixed(2)}</span>
          <button type="button" onClick={() => nudge(field, 0.05)}>+</button>
        </div>
      ))}
      <button
        type="button"
        className="danger"
        onClick={() => {
          edit((e) => ({ ...e, captions: { ...e.captions, words: e.captions.words.filter((_, i) => i !== index) } }));
          selectWord(null);
        }}
      >
        Delete word
      </button>
    </div>
  );
}
