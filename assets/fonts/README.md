# Fonts

* `NotoSans-*.ttf`, `NotoSansDevanagari-*.ttf` — Noto fonts from the Noto Project (github.com/notofonts), licensed under the SIL Open Font License 1.1. The full licence text is in `OFL.txt` (copied from `fonts/LICENSE` in github.com/notofonts/notofonts.github.io).
* `NyayaSetuSans-Regular.ttf`, `NyayaSetuSans-Bold.ttf` — the two families above merged into one font with fontTools
  (`fontTools.merge.Merger`, Devanagari first, then Latin). The PDF generator uses this merged font for both English and Hindi
  drafts, because fpdf2's per-glyph font fallback mis-shaped mixed Hindi/English lines (e.g. "अनुलग्नक A-1") during testing.
  The merged font is a derivative of OFL fonts and is distributed under the same licence (`OFL.txt`).

Used at run time: `NotoSans-Regular/Bold/Italic.ttf` and `NyayaSetuSans-Regular/Bold.ttf` (`utils/pdf_generator.py`, `docs/build_solution_pdf.py`).
`NotoSansDevanagari-*.ttf` are not loaded by the app; they are kept as the source files of the merged font.
