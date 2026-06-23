"""One-off: render TECHNICAL_REPORT_*.md to .txt and .pdf (fpdf2 + markdown)."""
import re
from pathlib import Path
import markdown
from fpdf import FPDF

HERE = Path(__file__).parent
SRC  = HERE / "TECHNICAL_REPORT_segmentation_and_pathplanning.md"
md_text = SRC.read_text(encoding="utf-8")

# ── 1. Plain-text version ─────────────────────────────────────────────
# Lightly strip markdown decoration for a clean .txt; keep structure.
txt = md_text
txt = re.sub(r"^#{1,6}\s*", "", txt, flags=re.M)      # heading hashes
txt = re.sub(r"\*\*(.+?)\*\*", r"\1", txt)             # bold
txt = re.sub(r"`([^`]+)`", r"\1", txt)                 # inline code
txt = re.sub(r"\[(.+?)\]\([^)]+\)", r"\1", txt)        # links -> text
(HERE / "TECHNICAL_REPORT_segmentation_and_pathplanning.txt").write_text(
    txt, encoding="utf-8")

# ── 2. PDF version ────────────────────────────────────────────────────
html = markdown.markdown(
    md_text,
    extensions=["tables", "fenced_code", "sane_lists"],
)

# fpdf2's write_html can't render <strong>/<em> nested inside table cells.
# Unwrap those tags within <td>/<th> only (keep bold/italic elsewhere).
def _strip_inline_in_cells(m):
    cell = m.group(0)
    return re.sub(r"</?(strong|em|b|i|code)>", "", cell)
html = re.sub(r"<t[dh][^>]*>.*?</t[dh]>", _strip_inline_in_cells, html,
              flags=re.S)

# write_html renders <code>/<pre> in the latin-1 core "courier" font (a
# reserved name that can't be remapped to a Unicode TTF). Transliterate the
# few non-latin-1 glyphs — mostly in the ASCII-art diagrams — to safe ASCII.
_ASCII = {
    "−": "-",  "→": "->", "←": "<-", "─": "-",
    "│": "|",  "├": "|",  "└": "\\", "┌": "/",
    "┐": "\\", "┘": "/",  "▼": "v",  "█": "#",
    "≥": ">=", "≤": "<=", "—": "-",  "–": "-",
    "✅": "[x]","⬜": "[ ]","“": '"',  "”": '"',
    "’": "'",  "‘": "'",
}
html = html.translate({ord(k): v for k, v in _ASCII.items()})

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
# Unicode-capable font (handles Kiên, arrows, etc.)
pdf.add_font("Arial", "",  r"C:\Windows\Fonts\arial.ttf")
pdf.add_font("Arial", "B", r"C:\Windows\Fonts\arialbd.ttf")
pdf.add_font("Arial", "I", r"C:\Windows\Fonts\ariali.ttf")
pdf.set_font("Arial", size=11)
pdf.write_html(html, font_family="Arial")

out = HERE / "TECHNICAL_REPORT_segmentation_and_pathplanning.pdf"
pdf.output(str(out))
print("Wrote:", out)
print("Wrote:", HERE / "TECHNICAL_REPORT_segmentation_and_pathplanning.txt")
