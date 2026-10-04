"""Render final PDFs for visual inspection; derived raster QA only."""
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw
from pypdf import PdfReader

PACKAGE = Path(__file__).resolve().parents[2]
POPPLER = Path("/Users/danial/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm")


def main():
    destination = Path(tempfile.mkdtemp(prefix="offline-review-20261003-", dir=PACKAGE / "tmp/pdfs"))
    for stem in ("main", "supplementary"):
        pdf = PACKAGE / "output/pdf" / (stem + ".pdf")
        subprocess.run([str(POPPLER), "-r", "100", "-png", str(pdf), str(destination / stem)], check=True)
        pages = sorted(destination.glob(stem + "-*.png"))
        assert len(pages) == len(PdfReader(pdf).pages)
        for offset in range(0, len(pages), 4):
            canvas = Image.new("RGB", (1040, 1530), "#e4e4e4")
            draw = ImageDraw.Draw(canvas)
            for n, path in enumerate(pages[offset:offset + 4]):
                with Image.open(path) as source:
                    source.thumbnail((500, 710))
                    x, y = 10 + 520 * (n % 2), 30 + 760 * (n // 2)
                    canvas.paste(source, (x, y))
                    draw.text((x, y - 20), path.stem, fill="black")
            canvas.save(destination / f"{stem}-contact-{offset // 4 + 1}.png")
        print(stem, len(pages), "pages")
        for index, page in enumerate(PdfReader(pdf).pages, 1):
            text = page.extract_text() or ""
            if any(phrase in text for phrase in ("Primary hardware comparison", "Decision-conditioned timing stages", "Primary per-run moving", "Direction-stratified primary", "Semantic-gate assay", "Hypothetical timing-offset")):
                print("Detailed inspection page", stem, index)
    print(destination)


if __name__ == "__main__":
    main()
