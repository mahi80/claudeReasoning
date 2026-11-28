---
name: xlsx
description: Create, read or edit Excel workbooks and CSV data with formulas, tables, charts and formatting; load for .xlsx or .xlsm tasks.
source: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/xlsx
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Excel workbooks

Use an installed openpyxl for formulas and formatting; pandas for bulk tabular work.
Check availability before relying on either. Never install automatically. Write a
workspace script; run_shell execution needs approval. write_file cannot write binary
workbooks. If execution is denied, deliver the script, not a claimed workbook.

## Preserve the input
- Save to a new filename. Read sheet names, dimensions, merged ranges, formulas,
  number formats and designated input cells before editing.
- Load once with data_only=False to retain formulas, and separately with
  data_only=True to inspect existing cached values. Never save the second copy:
  doing so replaces formulas with values.
- Use keep_vba=True for .xlsm, but never execute macros. Use rich_text=True where
  supported to preserve styled runs. openpyxl does not faithfully preserve every
  feature: inspect drawings, text boxes, slicers, external links and embedded parts
  first. If needed, edit selected OOXML cells instead or report the limitation.
- Only the top-left cell of a merged range is writable. Quote sheet names in
  references: ='Assumptions Inputs'!$B$5.
- Treat imported CSV strings beginning with =, +, -, or @ as potential spreadsheet
  formulas; store untrusted text as literal text unless formulas were requested.

## Build a usable model
- Keep exact requested sheet names, headers and calculations. Match existing style.
- Put assumptions in labeled input cells and reference them from formulas; do not
  replace calculated results with hardcoded Python values.
- Use formulas such as =SUM(B2:B9); check the first few manually before filling the
  grid. Anchor shared assumptions with $ and check first/last rows for range errors.
- Set number_format explicitly for dates, percentages and currencies. Percentages
  are fractions: 0.15 displays as 15%, while 15 displays as 1500%.
- Cite sources for supplied figures and label assumptions. New input templates need
  a brief input legend; do not insert sample rows into an existing user's workbook.
- Prefer compatible functions (SUMIFS, INDEX/MATCH, IFERROR) when the target engine
  is limited; verify version-specific functions and dynamic-array/spill support
  rather than assuming every Excel formula works in LibreOffice.
- Check duplicate/empty table headers, defined names and malformed number formats.

## Verification
1. Reopen the saved workbook in formula mode. Compare formulas, sheet names, data,
   styles and unaffected cells against the original.
2. openpyxl does not calculate formulas or populate cached values. Recalculate a
   disposable copy using an installed spreadsheet engine only with approval; use
   an isolated temporary profile and do not enable macros or external-link updates.
3. Read the recalculated copy in data_only mode. Count every error cell (#REF!,
   #DIV/0!, #VALUE!, #NAME?, #N/A, #NUM!, #NULL!) and compare with the original.
   A clean command exit is not evidence of an error-free workbook.
4. Check expected numeric results independently, including zero denominators,
   empty inputs and first/last periods. Error-free formulas can still be wrong.
5. Unsupported functions, missing caches and linked-workbook values remain
   unverified; report them explicitly, never silently replace formulas with values.
6. If no spreadsheet engine is available, deliver the workbook only after structural
   checks, clearly stating that formulas were not recalculated or visually checked.
