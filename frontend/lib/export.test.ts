import { describe, expect, it } from "vitest";

import { buildCsv, buildPlainTextTable, normalizeExportFileStem } from "@/lib/export";

describe("export helpers", () => {
  it("builds CSV with escaped values", () => {
    const csv = buildCsv([
      { metric: "Revenue", value: "1,234", note: 'He said "hi"' },
      { metric: "Margin", value: "12.50%", note: "line\nbreak" },
    ]);

    expect(csv).toBe([
      "metric,value,note",
      'Revenue,"1,234","He said ""hi"""',
      'Margin,12.50%,"line\nbreak"',
    ].join("\n"));
  });

  it("builds readable plaintext tables", () => {
    const table = buildPlainTextTable(
      ["Metric", "Value"],
      [
        ["Revenue", "$1.2B"],
        ["Margin", null],
      ]
    );

    expect(table).toBe([
      "Metric  | Value",
      "--------+------",
      "Revenue | $1.2B",
      "Margin  | -    ",
    ].join("\n"));
  });

  it("normalizes export filenames", () => {
    expect(normalizeExportFileStem(" BRK.B / test ")).toBe("BRK.B-test");
    expect(normalizeExportFileStem("   ", "fallback")).toBe("fallback");
  });
});