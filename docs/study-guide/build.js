// Builds the team study guide (.docx) from chapters/*.js and the measured results.
//   node build.js            -> CHAOS-OS-Study-Guide.docx
// Numbers come from ../paper/figures/results.json (make_figures.py) and facts.json.
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, Document, Footer, Header, HeadingLevel, LevelFormat, Packer, PageNumber, Paragraph,
  TableOfContents, TextRun,
} = require("docx");
const h = require("./lib");

const read = (file) => (fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {});
const R = read(path.join(__dirname, "..", "paper", "figures", "results.json"));
const F = read(path.join(__dirname, "facts.json"));

const chapters = fs.readdirSync(path.join(__dirname, "chapters")).filter((f) => f.endsWith(".js")).sort()
  .flatMap((f) => require(path.join(__dirname, "chapters", f))(h, R, F));

const cover = [
  new Paragraph({ spacing: { before: 2400, after: 0 }, children: [new TextRun({ text: "CHAOS OS", bold: true, size: 96, color: h.C.ink })] }),
  new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Break it. Learn from it. Build infrastructure that survives it.", size: 28, color: h.C.accent })] }),
  new Paragraph({
    spacing: { after: 600 }, border: { bottom: { style: "single", size: 12, color: h.C.accent, space: 12 } },
    children: [new TextRun({ text: "The complete project guide for the team: every component, every result, and how to explain it.", size: 26, color: h.C.ink2 })],
  }),
  ...[
    ["Team members", "[Name 1] · [Name 2] · [Name 3] · [Name 4]"],
    ["Course / department", "[Course name] · [Department, College]"],
    ["Project guide", "[Guide name]"],
    ["Date", "4 November 2026"],
    ["Repository", "https://github.com/Prarthan-B-P/chaos-os"],
  ].map(([k, v]) => new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text: `${k}:  `, bold: true, size: 22, color: h.C.ink }), new TextRun({ text: v, size: 22, color: h.C.ink2 })],
  })),
  new Paragraph({
    spacing: { before: 1200 },
    children: [new TextRun({ text: "Every number in this guide was measured in the lab and is generated from the experiment database.", italics: true, size: 20, color: h.C.muted })],
  }),
];

const toc = [
  new Paragraph({ pageBreakBefore: true, spacing: { after: 240 }, children: [new TextRun({ text: "Contents", bold: true, size: 40, color: h.C.ink })] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
];

// outlineLevel is what Word's table of contents reads; without it the TOC finds no entries.
const heading = (size, before, after, color = h.C.ink, outlineLevel) => ({
  run: { font: h.FONT, size, bold: true, color },
  paragraph: { spacing: { before, after }, keepNext: true, keepLines: true, outlineLevel },
});

const doc = new Document({
  creator: "CHAOS OS team",
  title: "CHAOS OS: complete project guide",
  description: "Study guide for the CHAOS OS resilience lab",
  features: { updateFields: true },
  styles: {
    default: {
      document: { run: { font: h.FONT, size: 22, color: h.C.ink } },
      title: heading(56, 0, 240),
      heading1: heading(36, 0, 200, h.C.ink, 0),
      heading2: heading(28, 300, 120, h.C.accent, 1),
      heading3: heading(24, 220, 80, h.C.ink2, 2),
    },
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [0, 1, 2].map((level) => ({
          level, format: LevelFormat.BULLET, text: ["•", "–", "·"][level], alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540 + level * 360, hanging: 270 } } },
        })),
      },
      {
        reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 300 } } } }],
      },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1440, bottom: 1300, left: 1440, right: 1440 } } },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
        new TextRun({ text: "CHAOS OS · project guide", size: 16, color: h.C.muted })] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], size: 16, color: h.C.muted })] })] }),
    },
    children: [...cover, ...toc, ...chapters],
  }],
});

const out = path.join(__dirname, "CHAOS-OS-Study-Guide.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log(`wrote ${out} (${(buf.length / 1024).toFixed(0)} KB)`);
});
