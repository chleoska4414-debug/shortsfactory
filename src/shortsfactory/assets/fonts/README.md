# Bundled fonts

## NanumGothic-Regular.ttf (default caption font)

shortsfactory ships **NanumGothic (Regular)** as the default burned-in caption font. It is
a CJK-capable TrueType font with full Korean/Hangul glyph coverage, which the micro-drama
mode requires: the Korean dialog and narration captions must render as real, distinct
glyphs. The previously bundled Noto Sans Regular (below) has **zero** Hangul coverage, so
every Hangul character rendered as the identical `.notdef` tofu box; NanumGothic fixes that.

`Config.font_path` (see `src/shortsfactory/config.py`, `_default_font_path()`) prefers this
font. Noto Sans and Pillow's DejaVuSans remain in the resolution chain as fallbacks.

- Font: NanumGothic, Regular weight
- Copyright: Copyright (c) 2010, NHN Corporation (http://www.nhncorp.com), with Reserved
  Font Name Nanum, Naver Nanum, NanumGothic, Naver NanumGothic
- License: SIL Open Font License, Version 1.1 (see `LICENSE-NanumGothic.txt` in this
  directory)

The SIL OFL-1.1 license permits redistribution of the font file with this project. The
full license text is included in `LICENSE-NanumGothic.txt`.

## NotoSans-Regular.ttf (Latin fallback)

shortsfactory ships **Noto Sans (Regular)** so burned-in captions render with a real,
scalable TrueType font on every install, with no network download and no dependency on a
system-installed font. This matters because some Pillow builds do not ship a bundled
`DejaVuSans.ttf`, in which case Pillow falls back to a tiny fixed-size bitmap font and
captions become illegible.

- Font: Noto Sans, Regular weight
- Copyright: Copyright The Noto Project Authors (https://github.com/notofonts/latin-greek-cyrillic)
- License: Apache License, Version 2.0 (see `LICENSE-NotoSans.txt` in this directory)

The Apache-2.0 license permits redistribution of the font file with this project. The full
license text is included in `LICENSE-NotoSans.txt`.
