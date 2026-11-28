---
name: pptx
description: Create, read or edit PowerPoint .pptx presentations and .potx templates, including layouts, charts and speaker notes.
source: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/pptx
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# PowerPoint presentations

Use installed pptxgenjs for new decks, python-pptx for reading or small edits, or
surgical OOXML changes for exact template preservation. write_file writes text,
not a binary presentation: write a workspace generator, then run it with approval.
Do not install packages automatically. If execution is denied or libraries are
missing, deliver the generator and clearly say no deck was produced.

## Design before generating
- Identify audience, purpose, slide count and whether it is live or a pre-read.
  Use one message per slide; lead with the conclusion when a decision is needed.
- Match a supplied template. Otherwise choose a consistent palette and typography,
  varied layouts, readable contrast and generous whitespace.
- Use native editable charts and text where possible. Set sensible font sizes;
  split content instead of shrinking it until unreadable.
- Give charts units, labels and real source attribution. Never invent results or
  download assets without authorization. Add narration through speaker notes.

## pptxgenjs footguns
- Set layout before slides. LAYOUT_16x9 is 10 x 5.625 inches; LAYOUT_WIDE is about
  13.333 x 7.5. Coordinates are not clamped: check every box stays on the canvas.
- Hex colors have six digits, no # or alpha. Use fill transparency (0..100), not
  an eight-digit color. Shadow opacity uses 0..1; offsets must not be negative.
- Create fresh option objects per add call: the library can mutate them in place.
- Use bullet options, not typed bullet characters; separate paragraphs correctly.
  Use charSpacing, not letterSpacing. Set margin: 0 for exact text alignment.
- Use isTextBox: true for non-placeholder text so assistive readers recognize it.
  Add notes through slide.addNotes; never hide narration in slide text boxes.
- Keep chart options compatible with the installed version. Stacked bars require
  internal data labels; secondary axes in combo charts need matching declarations
  for both value and category axes. A parser opening the deck is not enough QA.
- defineSlideMaster creates a reusable slide layout under the library's master.
  Check placeholder names and dimensions: misspellings can fail silently.
- One new presentation instance per output. Save to a new filename.

## Templates and editing
- Read slides, notes and relationships before editing. In python-pptx, replace
  individual run.text values where formatting matters; assigning text_frame.text
  collapses styled runs.
- Do not copy slide XML alone to duplicate a slide. Register relationships,
  content types and presentation slide IDs; charts may otherwise be shared with
  the original slide. Use a tested project helper or explain that duplication is
  not supported by the installed library.
- Change slide order through ppt/presentation.xml, not filename sorting. Retain
  namespace prefixes, relationships, layouts and masters when patching XML.
- For ZIP processing, bound entry count/uncompressed size and reject traversal,
  absolute paths and symlinks before extraction. Never execute embedded objects.
- Keep unrelated template elements; remove unused placeholders only when intended.

## Verification
Reopen output and check slide order, titles, notes, charts, relationships and missing
content. Render with installed LibreOffice if approved, then inspect every slide
for overlap, clipping and font substitution. Compare a template-derived deck with
its original. Structural parsing is not schema validation and a successful render
is not proof PowerPoint will accept chart XML. Report checks actually performed;
if no rendered slides were viewed, explicitly state visual QA is incomplete.
