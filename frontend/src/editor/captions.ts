import type { CaptionStyle, Word } from "./types";

/** A group of words shown together. Mirrored by the backend's ASS renderer. */
export interface CaptionPage {
  words: Word[];
  start: number;
  end: number;
}

const RULES: Record<Exclude<CaptionStyle, "none">, { maxWords: number; maxGap: number; breakAfter: RegExp }> = {
  "bold-highlight": { maxWords: 3, maxGap: 0.5, breakAfter: /[.?!,;:]$/ },
  clean: { maxWords: 7, maxGap: 0.7, breakAfter: /[.?!]$/ },
  boxed: { maxWords: 7, maxGap: 0.7, breakAfter: /[.?!]$/ },
};

/** Captions linger this long after their last word unless the next page starts. */
export const HOLD_SECONDS = 0.3;

export function paginate(words: Word[], style: CaptionStyle): CaptionPage[] {
  if (style === "none") return [];
  const rule = RULES[style];
  const pages: CaptionPage[] = [];
  let current: Word[] = [];
  const flush = () => {
    if (current.length) pages.push({ words: current, start: current[0].start, end: current[current.length - 1].end });
    current = [];
  };
  for (const word of words) {
    const last = current[current.length - 1];
    if (last && (current.length >= rule.maxWords || word.start - last.end > rule.maxGap)) flush();
    current.push(word);
    if (rule.breakAfter.test(word.text)) flush();
  }
  flush();
  return pages;
}

/** The page on screen at source time `t`, if any. */
export function pageAt(pages: CaptionPage[], t: number): CaptionPage | null {
  for (let i = pages.length - 1; i >= 0; i--) {
    const page = pages[i];
    if (page.start > t) continue;
    const next = pages[i + 1];
    const hideAt = Math.min(page.end + HOLD_SECONDS, next ? next.start : Infinity);
    return t < hideAt ? page : null;
  }
  return null;
}
