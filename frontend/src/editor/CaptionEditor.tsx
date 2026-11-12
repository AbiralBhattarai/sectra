import { useEffect, useMemo, useState } from "react";
import { run } from "./commands";
import { clock } from "./Preview";
import { captionCues } from "./sequence";
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
  const { selectWord, seek } = useEditor.getState();
  const words = edl.captions.words;
  // Listed in the style's grouping, but "none" still lists words to edit.
  const cues = useMemo(() => captionCues(edl, edl.captions.style === "none" ? "clean" : edl.captions.style), [edl]);

  return (
    <div className="tab-body">
      <label className="field">
        Caption style
        <select value={edl.captions.style} onChange={(event) => run({ op: "update_clip", caption_style: event.target.value as CaptionStyle })}>
          {STYLES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {selected != null && words[selected] && <WordForm index={selected} word={words[selected]} />}

      <ol className="caption-pages">
        {cues.map((cue) => (
          <li key={`${cue.start}-${cue.words[0].index}`}>
            <span className="stage">{clock(cue.start)}</span>
            <span>
              {cue.words.map((word) => (
                <button
                  type="button"
                  key={`${word.start}-${word.index}`}
                  className={`word${selected === word.index ? " selected" : ""}`}
                  onClick={() => {
                    selectWord(word.index);
                    seek(word.start);
                  }}
                >
                  {word.text}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ol>
      {cues.length === 0 && <p className="placeholder">No words in this clip.</p>}
      <button type="button" className="small" onClick={() => run({ op: "restore_words" })} title="Refill every caption from the transcript, discarding edits">
        Restore all words from the transcript
      </button>
    </div>
  );
}

function WordForm({ index, word }: { index: number; word: Word }) {
  const selectWord = useEditor((s) => s.selectWord);
  const [text, setText] = useState(word.text);
  useEffect(() => setText(word.text), [word]);

  return (
    <div className="word-form">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => text.trim() && text !== word.text && run({ op: "edit_words", words: [{ index, text: text.trim() }] })}
        onKeyDown={(event) => event.key === "Enter" && (event.target as HTMLInputElement).blur()}
        aria-label="Word text"
      />
      <button
        type="button"
        className="danger"
        onClick={() => {
          selectWord(null);
          void run({ op: "delete_words", indices: [index] });
        }}
      >
        Delete word
      </button>
    </div>
  );
}
