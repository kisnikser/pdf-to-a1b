# /// script
# requires-python = ">=3.11"
# dependencies = ["pikepdf"]
# ///
"""Convert a PDF to PDF/A-1b without rasterizing whole pages or dropping links."""

import subprocess
import sys
import tempfile
from pathlib import Path

import pikepdf
from pikepdf import Name

GS = ["gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER"]
PDFA_DEF = """
(../iccprofiles/srgb.icc) findlibfile pop exch pop /icc exch def
[/_objdef {icc} /type /stream /OBJ pdfmark
[{icc} << /N 3 >> /PUT pdfmark
[{icc} icc /PUT pdfmark
[/_objdef {oi} /type /dict /OBJ pdfmark
[{oi} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {icc} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{Catalog} << /OutputIntents [ {oi} ] >> /PUT pdfmark
"""


def transparent(obj: pikepdf.Object, seen: set) -> bool:
    """True if a page or form, or anything it draws, uses transparency, which PDF/A-1 forbids."""
    if obj.objgen in seen:
        return False
    seen.add(obj.objgen)
    res = obj.get("/Resources", {})
    for gs in res.get("/ExtGState", {}).values():
        if float(gs.get("/ca", 1)) < 1 or float(gs.get("/CA", 1)) < 1:
            return True
        if gs.get("/SMask", Name.None_) != Name.None_ or gs.get("/BM", Name.Normal) not in (
            Name.Normal,
            Name.Compatible,
        ):
            return True
    for x in res.get("/XObject", {}).values():
        if "/SMask" in x or (x.get("/Subtype") == Name.Form and transparent(x, seen)):
            return True
    return False


def rasterize(pdf: pikepdf.Pdf, form: pikepdf.Stream, tmp: Path, dpi: int) -> None:
    """Replace a form XObject's content with an image of itself rendered on white at the given DPI."""
    x0, y0, x1, y1 = (float(v) for v in form.BBox)
    one = pikepdf.new()
    one.add_blank_page(page_size=(x1 - x0, y1 - y0))
    one.pages[0].MediaBox = pikepdf.Array([x0, y0, x1, y1])
    fig = one.copy_foreign(form)
    if "/Matrix" in fig:
        del fig["/Matrix"]
    one.pages[0].Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(F=fig))
    one.pages[0].Contents = one.make_stream(b"/F Do")
    one.save(tmp / "fig.pdf")
    subprocess.run([*GS, "-sDEVICE=pdfimage24", f"-r{dpi}", "-o", tmp / "img.pdf", tmp / "fig.pdf"], check=True)
    with pikepdf.open(tmp / "img.pdf") as img:
        raster = pdf.copy_foreign(img.pages[0].as_form_xobject())
    form.write(f"q 1 0 0 1 {x0} {y0} cm /R Do Q".encode())
    form.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(R=raster))


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: a1b.py in.pdf [out.pdf]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) == 3 else src.with_name(f"{src.stem}_pdfa.pdf")
    with pikepdf.open(src) as pdf, tempfile.TemporaryDirectory() as tmp:
        done = {}  # objgen of a transparent XObject -> its opaque replacement
        for n, page in enumerate(pdf.pages, 1):
            for annot in page.get("/Annots", []):
                # PDF/A-1 requires Print on and Invisible, Hidden, NoView off
                annot.F = (int(annot.get("/F", 0)) | 4) & ~(1 | 2 | 32)
            xobjects = page.get("/Resources", {}).get("/XObject", {})
            for key, x in list(xobjects.items()):
                if x.objgen not in done:
                    if x.get("/Subtype") == Name.Image and "/SMask" in x:
                        # An image with alpha, e.g. an RGBA PNG: wrap it in a form and flatten at native resolution
                        w, h = int(x.Width), int(x.Height)
                        done[x.objgen] = pdf.make_stream(
                            f"q {w} 0 0 {h} 0 0 cm /I Do Q".encode(),
                            Type=Name.XObject,
                            Subtype=Name.Form,
                            BBox=[0, 0, w, h],
                            Matrix=[1 / w, 0, 0, 1 / h, 0, 0],
                            Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(I=x)),
                        )
                        rasterize(pdf, done[x.objgen], Path(tmp), dpi=72)
                    elif x.get("/Subtype") == Name.Form and transparent(x, set()):
                        rasterize(pdf, x, Path(tmp), dpi=600)
                        done[x.objgen] = x
                    else:
                        continue
                xobjects[key] = done[x.objgen]
            if transparent(page.obj, set()):
                print(f"page {n}: transparency outside figures, Ghostscript will rasterize the page", file=sys.stderr)
        for obj in pdf.objects:  # PDF/A-1 forbids transparency groups, and Ghostscript rasterizes pages with them
            if isinstance(obj, pikepdf.Dictionary | pikepdf.Stream) and "/Group" in obj:
                del obj["/Group"]
        pdf.save(Path(tmp) / "in.pdf")
        subprocess.run(
            [
                *GS,
                "-dPDFA=1",
                "-dPDFACompatibilityPolicy=1",
                "-sColorConversionStrategy=RGB",
                "-dAutoFilterColorImages=false",  # keep images lossless instead of recompressing them as JPEG
                "-dAutoFilterGrayImages=false",
                "-sColorImageFilter=FlateEncode",
                "-sGrayImageFilter=FlateEncode",
                "-sDEVICE=pdfwrite",
                "-o",
                dst,
                "-c",
                PDFA_DEF,
                "-f",
                Path(tmp) / "in.pdf",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
