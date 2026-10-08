import { describe, expect, it } from "vitest";
import en from "@/i18n/messages/en.json";
import hi from "@/i18n/messages/hi.json";
import te from "@/i18n/messages/te.json";
import { formatDuration, formatINR, formatKg, formatKm, toQuery } from "@/lib/utils";

const flat = (o: object, p = ""): Record<string, string> =>
  Object.entries(o).reduce<Record<string, string>>((acc, [k, v]) => {
    if (v && typeof v === "object") Object.assign(acc, flat(v, `${p}${k}.`));
    else acc[`${p}${k}`] = String(v);
    return acc;
  }, {});

describe("formatters", () => {
  it("formats weights, keeping grams when exact", () => {
    expect(formatKg(541.28)).toBe("541.3 kg");
    expect(formatKg(541.28, "en", true)).toBe("541.28 kg");
    expect(formatKg(2.456)).toBe("2.46 kg");
    expect(formatKg(1636.1)).toBe("1.64 t");
    expect(formatKg(null)).toBe("—");
  });
  it("formats distance, duration and money (paise)", () => {
    expect(formatKm(13700)).toBe("13.7 km");
    expect(formatDuration(3960)).toBe("1 h 06 min");
    expect(formatDuration(2520)).toBe("42 min");
    expect(formatINR(1700000)).toMatch(/17,000/);
  });
  it("builds query strings without empty values", () => {
    expect(toQuery({ a: 1, b: undefined, c: null, d: "x y" })).toBe("?a=1&d=x+y");
  });
});

describe("translations", () => {
  const e = flat(en);
  it.each([["hi", flat(hi)], ["te", flat(te)]])("%s has exactly the English keys and placeholders", (_, other) => {
    expect(Object.keys(other).sort()).toEqual(Object.keys(e).sort());
    for (const [k, v] of Object.entries(e)) {
      const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
      expect(ph(other[k]), k).toEqual(ph(v));
    }
  });
});
