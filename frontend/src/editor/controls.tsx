import { useEffect, useState } from "react";

/** A range input that only commits (one edit) when released. */
export function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onCommit: (value: number) => unknown;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState<number | null>(null);
  const value = draft ?? props.value;
  const commit = () => {
    if (draft != null && draft !== props.value) void props.onCommit(draft);
    setDraft(null);
  };
  return (
    <label className="field slider">
      <span>
        {props.label} <span className="stage">{props.format ? props.format(value) : value}</span>
      </span>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={value}
        disabled={props.disabled}
        onChange={(event) => setDraft(Number(event.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
      />
    </label>
  );
}

/** A number input that commits on Enter or when it loses focus. */
export function NumberField(props: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onCommit: (value: number) => unknown;
}) {
  const [text, setText] = useState(format(props.value));
  useEffect(() => setText(format(props.value)), [props.value]);
  const commit = () => {
    const value = Number(text);
    if (!Number.isFinite(value) || value === props.value) return setText(format(props.value));
    void props.onCommit(value);
  };
  return (
    <label className="field number">
      {props.label}
      <input
        type="number"
        value={text}
        min={props.min}
        max={props.max}
        step={props.step ?? 0.1}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => event.key === "Enter" && (event.target as HTMLInputElement).blur()}
      />
    </label>
  );
}

const format = (value: number) => String(Math.round(value * 1000) / 1000);
