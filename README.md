# pdf-to-a1b

[![PDF/A-1b](https://img.shields.io/badge/PDF%2FA-1b-d32f2f)](https://www.pdfa.org/resource/iso-19005-1-pdf-a-1/)
[![veraPDF](https://img.shields.io/badge/veraPDF-PASS-2e7d32)](https://verapdf.org)
[![Ghostscript](https://img.shields.io/badge/Ghostscript-10.x-1565c0)](https://ghostscript.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab)](a1b.py)

A single script that converts a PDF to PDF/A-1b, the archival format dissertation councils require, without touching the source file.

## Usage

```sh
brew install ghostscript uv
uv run a1b.py thesis.pdf              # writes thesis_pdfa.pdf
uv run a1b.py thesis.pdf out.pdf
```

Validate with [veraPDF](https://verapdf.org):

```sh
docker run --rm -v "$PWD":/data verapdf/cli --flavour 1b --format text /data/thesis_pdfa.pdf
```

## How it works

[`a1b.py`](a1b.py) fixes a temporary copy with `pikepdf`, then runs Ghostscript's `pdfwrite` with `-dPDFA=1` and Ghostscript's bundled `srgb.icc` as the output intent.

- **Links stay clickable.** PDF/A-1 requires the Print flag on every annotation, and Ghostscript drops annotations without it, so the script sets the flag on all of them.
- **Only figures with transparency become images.** PDF/A-1 forbids transparency, and Ghostscript flattens it by rasterizing the whole page, text included. The script instead renders each figure (form XObject) that uses transparency into a 600 dpi image on white, and each image with an alpha channel (e.g. an RGBA PNG) onto white at its native resolution, so body text, formulas, and links stay vector.
- **Images stay lossless.** Ghostscript recompresses images as JPEG by default; the script keeps them Flate-encoded.

## Gotchas

- **Text inside a figure with transparency is no longer selectable.** Axis labels of such plots become pixels; the body text is unaffected.
- **The 600 dpi is measured at the figure's own size.** A figure scaled up 2× in LaTeX ends up at 300 dpi on the page.
- **Transparency drawn directly on the page, outside a figure, still rasterizes that page and drops its links.** The script prints `page N: transparency outside figures` for each such page; in LaTeX this comes from TikZ `opacity`.
- **Docker Desktop on macOS does not mount `/tmp`.** Keep the file under `$HOME` when validating with veraPDF, or it reports "File doesn't exist".
