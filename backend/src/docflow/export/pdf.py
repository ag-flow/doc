"""Export PDF d'un document (et de ses enfants, dans l'ordre choisi).

Le rendu vise la feuille Broadsheet de l'écran : mêmes encres (ink/cyan),
mêmes filets (citations 4px cyan, tableaux réglés, code sur fond teinté).
Les blocs custom (```df-*, mermaid) se dégradent en bloc de code lisible —
même règle qu'à l'écran pour un composant inconnu, jamais de perte.
"""

from __future__ import annotations

import html
import re
import uuid
from pathlib import Path

import asyncpg
import markdown as md
from fastapi import HTTPException

from docflow.db.helpers import require_workspace

# Police de l'écran (Source Serif 4), embarquée dans l'image (deploy/Dockerfile)
# ou lue depuis node_modules en dev. Absente → repli Georgia/DejaVu Serif.
_FONT_DIRS = [
    Path("/app/fonts"),
    Path(__file__).resolve().parents[4]
    / "frontend/node_modules/@fontsource-variable/source-serif-4/files",
]


def _font_faces() -> str:
    for base in _FONT_DIRS:
        normal = base / "source-serif-4-latin-wght-normal.woff2"
        italic = base / "source-serif-4-latin-wght-italic.woff2"
        if normal.is_file():
            faces = (
                '@font-face { font-family: "Source Serif 4"; font-style: normal; '
                f"src: url(\"file://{normal}\"); }}\n"
            )
            if italic.is_file():
                faces += (
                    '@font-face { font-family: "Source Serif 4"; font-style: italic; '
                    f"src: url(\"file://{italic}\"); }}\n"
                )
            return faces
    return ""

# Palette Broadsheet (tokens.css) — le PDF s'imprime sur blanc, l'encre et le
# cyan d'accent sont ceux de l'écran.
_CSS = """
@page {
  size: A4;
  margin: 22mm 18mm;
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 9px; color: #8a8886; }
}
body {
  font-family: "Source Serif 4", Georgia, "DejaVu Serif", serif;
  color: #201e1d;
  font-size: 11.5pt;
  line-height: 1.62;
}
section.doc-next { page-break-before: always; }
h1 { font-size: 24pt; line-height: 1.1; letter-spacing: -0.02em; margin: 0 0 14pt; }
h2 { font-size: 16pt; margin: 18pt 0 7pt; }
h3 { font-size: 13pt; margin: 14pt 0 5pt; }
p { margin: 0 0 8pt; }
a { color: #0088b0; text-decoration: none; }
blockquote {
  border-left: 4px solid #0088b0;
  padding-left: 12pt;
  margin: 12pt 0;
  color: rgba(32, 30, 29, 0.72);
}
code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 0.85em;
  background: rgba(32, 30, 29, 0.06);
  padding: 0 2pt;
}
pre {
  background: rgba(32, 30, 29, 0.05);
  padding: 8pt;
  font-size: 8.5pt;
  line-height: 1.45;
  white-space: pre-wrap;
  word-wrap: break-word;
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 10pt 0; font-size: 10pt; }
th { text-align: left; border-bottom: 1.5pt solid #201e1d; padding: 3pt 6pt; }
td { border-bottom: 0.5pt solid rgba(32, 30, 29, 0.18); padding: 3pt 6pt; }
ul, ol { margin: 0 0 8pt; padding-left: 16pt; }
li { margin-bottom: 3pt; }
hr { border: none; border-top: 0.5pt solid rgba(32, 30, 29, 0.25); margin: 14pt 0; }
img { max-width: 100%; }
.signatures {
  margin-top: 28pt;
  padding-top: 10pt;
  border-top: 1.5pt solid #201e1d;
  page-break-inside: avoid;
}
.signatures h2 { margin-top: 0; }
.signatures table { table-layout: fixed; }
.signatures td {
  height: 52pt; vertical-align: bottom;
  border-bottom: 0.5pt solid rgba(32, 30, 29, 0.4);
}
.signatures .sig-label {
  height: auto; border: none; font-size: 8.5pt;
  text-transform: uppercase; letter-spacing: 0.06em; color: rgba(32, 30, 29, 0.55);
}
"""

_MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]

_SIGNATURES_HTML = """
<div class="signatures">
  <h2>Signatures</h2>
  <table>
    <tr>
      <td class="sig-label">Nom</td>
      <td class="sig-label">Date</td>
      <td class="sig-label">Signature</td>
    </tr>
    <tr><td></td><td></td><td></td></tr>
  </table>
</div>
"""


def strip_title_heading(content: str, title: str) -> str:
    """Retire un « # <titre> » de tête strictement égal au titre du document —
    même règle que la lecture à l'écran : le titre n'apparaît qu'une fois."""
    m = re.match(r"\s*#\s+(.+?)\s*\n", content)
    if m and m.group(1).strip() == title.strip():
        return content[m.end():].lstrip("\n")
    return content


def build_html(docs: list[tuple[str, str]], *, signed: bool) -> str:
    """Assemble le HTML du PDF : chaque document = son titre puis son contenu,
    saut de page entre documents ; cadre de signatures en fin si demandé."""
    sections: list[str] = []
    for i, (title, content) in enumerate(docs):
        body = md.markdown(strip_title_heading(content or "", title), extensions=_MD_EXTENSIONS)
        cls = "doc" if i == 0 else "doc doc-next"
        sections.append(
            f'<section class="{cls}"><h1>{html.escape(title)}</h1>{body}</section>'
        )
    if signed:
        sections.append(_SIGNATURES_HTML)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{_font_faces()}{_CSS}</style></head><body>"
        + "".join(sections)
        + "</body></html>"
    )


async def fetch_export_docs(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    child_ids: list[uuid.UUID],
) -> tuple[str, list[tuple[str, str]]]:
    """Charge le document racine puis les enfants demandés, DANS L'ORDRE reçu.

    Chaque enfant doit être un enfant direct du document et du même workspace
    (422 sinon) — l'ordre est celui choisi par l'utilisateur, pas celui de
    l'arbre. Retourne (nom de fichier sans extension, [(titre, contenu)]).
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        root = await conn.fetchrow(
            "SELECT d.title, d.slug, dv.content FROM document d "
            "LEFT JOIN document_version dv ON dv.document_ref = d.doc_technical_key "
            "  AND dv.version_number = d.version "
            "WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2",
            doc_id,
            wk,
        )
        if root is None:
            raise HTTPException(404, f"document {doc_id} introuvable")
        docs: list[tuple[str, str]] = [(root["title"], root["content"] or "")]
        for child_id in child_ids:
            child = await conn.fetchrow(
                "SELECT d.title, dv.content FROM document d "
                "LEFT JOIN document_version dv ON dv.document_ref = d.doc_technical_key "
                "  AND dv.version_number = d.version "
                "WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2 "
                "  AND d.parent = $3",
                child_id,
                wk,
                doc_id,
            )
            if child is None:
                raise HTTPException(
                    422, f"{child_id} n'est pas un enfant direct du document"
                )
            docs.append((child["title"], child["content"] or ""))
    filename = root["slug"] or _slug_from_title(root["title"])
    return filename, docs


def _slug_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "document"


def render_pdf(html_doc: str) -> bytes:
    # Import local : WeasyPrint tire Pango — chargé seulement à l'export.
    from weasyprint import HTML  # type: ignore[import-untyped]

    return bytes(HTML(string=html_doc).write_pdf())
