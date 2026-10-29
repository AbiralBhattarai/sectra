import { describe, expect, it } from "vitest";
import { pageAt, paginate } from "./captions";
import type { Word } from "./types";

const words = (...specs: [string, number, number][]): Word[] =>
  specs.map(([text, start, end]) => ({ text, start, end }));

const texts = (pages: ReturnType<typeof paginate>) => pages.map((p) => p.words.map((w) => w.text).join(" "));

describe("paginate", () => {
  const sample = words(
    ["one", 0, 0.3],
    ["two", 0.3, 0.6],
    ["three", 0.6, 0.9],
    ["four.", 0.9, 1.2],
    ["five", 2.5, 2.8],
    ["six", 2.8, 3.1],
  );

  it("bold-highlight shows at most three words and breaks on punctuation and pauses", () => {
    expect(texts(paginate(sample, "bold-highlight"))).toEqual(["one two three", "four.", "five six"]);
  });

  it("clean lines run until a sentence ends or a long pause", () => {
    expect(texts(paginate(sample, "clean"))).toEqual(["one two three four.", "five six"]);
  });

  it("none shows nothing", () => {
    expect(paginate(sample, "none")).toEqual([]);
  });
});

describe("pageAt", () => {
  const pages = paginate(words(["a", 0, 0.5], ["b.", 0.5, 1], ["c", 3, 3.5]), "bold-highlight");

  it("finds the page being spoken and holds it briefly after", () => {
    expect(pageAt(pages, 0.7)?.words[0].text).toBe("a");
    expect(pageAt(pages, 1.2)?.words[0].text).toBe("a");
    expect(pageAt(pages, 2)).toBeNull();
    expect(pageAt(pages, 3.1)?.words[0].text).toBe("c");
    expect(pageAt(pages, -1)).toBeNull();
  });
});
