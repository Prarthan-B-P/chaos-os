// Building blocks for the study guide (docx-js). Content lives in chapters/*.js.
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, HeadingLevel, ImageRun, LevelFormat, PageBreak, Paragraph,
  ShadingType, Table, TableCell, TableRow, TextRun, WidthType,
} = require("docx");

const C = {
  ink: "0E0E0F", ink2: "47464A", muted: "6B6965", line: "CDC9C2", sunken: "F3F1ED",
  accent: "C84A18", accentSoft: "FDF0EA", good: "106E10", goodSoft: "EEF8EE", warnSoft: "FFF4DC",
  blueSoft: "E8F1FB",
};
const FONT = "Calibri";
const MONO = "Consolas";
const TEXT_WIDTH = 9026; // A4 (11906 DXA) minus 1-inch margins

// **bold**, `code` and _italic_ inside a string become separate runs.
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: 19, color: C.accent, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const H1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)], pageBreakBefore: true });
const H2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const H3 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 120, line: 288 }, ...opts });
const Lead = (text) => new Paragraph({ children: runs(text, { size: 24, color: C.ink2 }), spacing: { after: 160, line: 300 } });

const bullets = (items, level = 0) => items.flatMap((item) => Array.isArray(item)
  ? bullets(item, level + 1)
  : [new Paragraph({ numbering: { reference: "bullets", level }, children: runs(item), spacing: { after: 60, line: 276 } })]);

let numberedInstance = 0;
const numbered = (items) => {
  numberedInstance += 1;
  return items.map((item) => new Paragraph({
    numbering: { reference: "numbers", level: 0, instance: numberedInstance }, children: runs(item),
    spacing: { after: 60, line: 276 },
  }));
};

// A shaded box with a title line: kind = explain | remember | warn | question.
function callout(kind, title, lines) {
  const styles = {
    explain: { fill: C.accentSoft, bar: C.accent },
    remember: { fill: C.sunken, bar: C.ink2 },
    warn: { fill: C.warnSoft, bar: "855600" },
    question: { fill: C.blueSoft, bar: "1C5CAB" },
  }[kind];
  const box = (children, extra = {}) => new Paragraph({
    children, shading: { type: ShadingType.CLEAR, color: "auto", fill: styles.fill },
    border: { left: { style: BorderStyle.SINGLE, size: 24, color: styles.bar, space: 8 } },
    indent: { left: 200, right: 120 }, spacing: { after: 0, line: 276 }, ...extra,
  });
  const body = (Array.isArray(lines) ? lines : [lines]);
  return [
    box([new TextRun({ text: title.toUpperCase(), bold: true, size: 18, color: styles.bar })], { spacing: { before: 160, after: 40 } }),
    ...body.map((l, i) => box(runs(l), { spacing: { after: i === body.length - 1 ? 200 : 60, line: 276 } })),
  ];
}

function code(lines) {
  return lines.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l || " ", font: MONO, size: 18, color: C.ink })],
    shading: { type: ShadingType.CLEAR, color: "auto", fill: C.sunken },
    indent: { left: 200, right: 200 },
    spacing: { before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 160 : 0, line: 240 },
  }));
}

function cell(text, width, { header = false, fill, align, keepNext = false } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: header ? C.ink : fill || "FFFFFF" },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: String(text).split("\n").map((t) => new Paragraph({
      alignment: align || AlignmentType.LEFT, keepNext,
      children: runs(t, header ? { bold: true, color: "FFFFFF", size: 19 } : { size: 19 }),
      spacing: { after: 0, line: 252 },
    })),
  });
}

// widths: relative weights, scaled to the text width.
function table(headers, rows, weights, { zebra = true, highlight } = {}) {
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((w) => Math.floor((w / total) * TEXT_WIDTH));
  widths[widths.length - 1] += TEXT_WIDTH - widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: C.line };
  // Short tables stay on one page (keep-with-next on every row but the last).
  const keep = rows.length <= 12;
  return new Table({
    width: { size: TEXT_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    borders: { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border },
    rows: [
      new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, widths[i], { header: true, keepNext: true })) }),
      ...rows.map((r, ri) => new TableRow({
        cantSplit: true,
        children: r.map((v, i) => cell(v, widths[i], {
          fill: highlight && highlight(r, ri) ? C.goodSoft : zebra && ri % 2 ? "FAF9F7" : "FFFFFF",
          keepNext: keep && ri < rows.length - 1,
        })),
      })),
    ],
  });
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

let figureNo = 0;
function figure(file, caption, widthIn = 6.2) {
  if (!fs.existsSync(file)) {
    return [P(`[figure missing: ${path.basename(file)}]`)];
  }
  figureNo += 1;
  const { w, h } = pngSize(file);
  const width = Math.round(widthIn * 96);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width, height: Math.round((width * h) / w) } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: `Figure ${figureNo}. `, bold: true, size: 18, color: C.ink2 }), ...runs(caption, { size: 18, color: C.ink2 })],
    }),
  ];
}

const spacer = (pts = 6) => new Paragraph({ children: [], spacing: { after: pts * 20 } });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// Number formatting for results pulled from results.json.
const s1 = (x) => (x == null ? "–" : `${Number(x).toFixed(1)} s`);
const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);

module.exports = {
  C, FONT, MONO, TEXT_WIDTH, runs, H1, H2, H3, P, Lead, bullets, numbered, callout, code, table,
  figure, spacer, pageBreak, s1, pct,
};
