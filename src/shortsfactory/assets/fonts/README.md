# Bundled fonts

## NotoSans-Regular.ttf

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
