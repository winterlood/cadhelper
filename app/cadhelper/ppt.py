"""PowerPoint: 고객 설명용 제안서·시공 계획 발표자료 (.pptx, 16:9).

Codex gives a list of slides; each slide can have bullets, one image
(capture_view / sketchup_capture / 사진), a table (면적표·견적 요약), or an image
with bullets beside it. Output goes to the open 현장's 결과물 folder (or
work\\결과물); nothing existing is overwritten.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from . import safety
from .learn import load_profile

FONT = "맑은 고딕"
INK = RGBColor(0x1C, 0x25, 0x2D)
MUTED = RGBColor(0x5B, 0x68, 0x73)
ACCENT = RGBColor(0xC4, 0x12, 0x2F)
LINE = RGBColor(0xD5, 0xDB, 0xE0)
HEAD = RGBColor(0xE9, 0xEE, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)


def _new_path(filename: str) -> Path:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(filename).stem or "발표자료")
    out = safety.out_dir()
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{stem}.pptx"
    n = 2
    while p.exists():
        p = out / f"{stem} ({n}).pptx"
        n += 1
    return p


def _text(slide, x, y, w, h, text, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = str(line)
        r.font.name = FONT
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
    return tb


def _rect(slide, x, y, w, h, color):
    from pptx.enum.shapes import MSO_SHAPE
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def _bullets(slide, x, y, w, h, items, size=20):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        sub = isinstance(item, str) and item.startswith(("  ", "-  ", "- -"))
        txt = str(item).strip().lstrip("-• ").strip()
        p.space_after = Pt(10 if not sub else 4)
        r1 = p.add_run()
        r1.text = ("–  " if sub else "■  ")
        r1.font.name = FONT
        r1.font.size = Pt(size - (4 if sub else 6))
        r1.font.color.rgb = MUTED if sub else ACCENT
        r2 = p.add_run()
        r2.text = txt
        r2.font.name = FONT
        r2.font.size = Pt(size - (3 if sub else 0))
        r2.font.color.rgb = MUTED if sub else INK
        if sub:
            p.level = 1


def _picture(slide, path: str, x, y, w, h):
    p = Path(path)
    if not p.is_absolute():
        p = safety.out_dir() / p
    if not p.is_file():
        raise FileNotFoundError(f"그림 파일이 없습니다: {p}")
    from PIL import Image
    with Image.open(p) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    slide.shapes.add_picture(str(p), x + (w - pw) // 2, y + (h - ph) // 2, pw, ph)


def _table(slide, rows, x, y, w, h, size=14):
    rows = [[("" if c is None else c) for c in r] for r in rows if r is not None]
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    rows = [list(r) + [""] * (ncol - len(r)) for r in rows]
    row_h = min(Inches(0.5), Emu(int(h / max(len(rows), 1))))
    shape = slide.shapes.add_table(len(rows), ncol, x, y, w, row_h * len(rows))
    tbl = shape.table
    for ri, r in enumerate(rows):
        for ci, val in enumerate(r):
            cell = tbl.cell(ri, ci)
            if isinstance(val, float):
                val = f"{val:,.2f}".rstrip("0").rstrip(".")
            elif isinstance(val, int):
                val = f"{val:,}"
            cell.text = str(val)
            para = cell.text_frame.paragraphs[0]
            num = bool(re.fullmatch(r"[-+]?[\d,]+(\.\d+)?\s*(원|㎡|평|m|mm|개|%)?", str(val).strip()))
            para.alignment = PP_ALIGN.RIGHT if (num and ri > 0) else (PP_ALIGN.CENTER if ri == 0 else PP_ALIGN.LEFT)
            for run in para.runs:
                run.font.name = FONT
                run.font.size = Pt(size)
                run.font.bold = ri == 0
                run.font.color.rgb = INK
            total_row = ri > 0 and bool(re.match(r"\s*(합\s*계|총|소\s*계|공급가액|부가세)", str(r[0])))
            if total_row:
                for run in para.runs:
                    run.font.bold = True
            cell.fill.solid()
            cell.fill.fore_color.rgb = HEAD if ri == 0 else (RGBColor(0xF1, 0xF3, 0xF5) if total_row or ri % 2 == 0 else WHITE)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE


def build_ppt(filename: str, title: str, slides: list, subtitle: str = "", client: str = "") -> Path:
    if not slides:
        raise ValueError("slides 가 비어 있습니다. 최소 한 장은 있어야 합니다.")
    prof = load_profile()
    company = prof.get("company", "")
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]

    # 표지
    s = prs.slides.add_slide(blank)
    _rect(s, 0, 0, W, H, INK)
    _rect(s, MARGIN, Inches(3.05), Inches(0.9), Inches(0.08), ACCENT)
    _text(s, MARGIN, Inches(1.7), W - 2 * MARGIN, Inches(1.3), title, 40, True, WHITE, anchor=MSO_ANCHOR.BOTTOM)
    sub = " · ".join(x for x in [subtitle, f"{client} 귀하" if client else ""] if x)
    if sub:
        _text(s, MARGIN, Inches(3.3), W - 2 * MARGIN, Inches(0.8), sub, 22, False, RGBColor(0xC9, 0xD1, 0xD8))
    foot = "   ".join(x for x in [company, prof.get("phone", ""), str(date.today())] if x)
    _text(s, MARGIN, H - Inches(1.1), W - 2 * MARGIN, Inches(0.5), foot, 14, False, RGBColor(0x9A, 0xA6, 0xB0))

    total = len(slides)
    for idx, sd in enumerate(slides, 1):
        if isinstance(sd, str):
            sd = {"title": sd}
        s = prs.slides.add_slide(blank)
        _rect(s, 0, 0, Inches(0.18), H, ACCENT)
        _text(s, MARGIN, Inches(0.35), W - 2 * MARGIN, Inches(0.8), sd.get("title", ""), 30, True)
        _rect(s, MARGIN, Inches(1.15), W - 2 * MARGIN, Emu(9525), LINE)
        top, bottom = Inches(1.45), H - Inches(0.75)
        bx, bw, bh = MARGIN, W - 2 * MARGIN, bottom - top
        bullets = sd.get("bullets") or []
        image = sd.get("image")
        table = sd.get("table")
        if image and (bullets or table):
            iw = int(bw * 0.58)
            _picture(s, image, bx, top, iw, bh)
            rx, rw = bx + iw + Inches(0.35), bw - iw - Inches(0.35)
            if table:
                _table(s, table, rx, top, rw, bh, 12)
                if bullets:
                    _bullets(s, rx, top + Inches(0.5) * len(table) + Inches(0.3), rw, Inches(2), bullets, 16)
            else:
                _bullets(s, rx, top, rw, bh, bullets, 18)
        elif image:
            _picture(s, image, bx, top, bw, bh)
        elif table:
            th = Inches(0.5) * len(table)
            _table(s, table, bx, top, bw, bh, 14)
            if bullets:
                _bullets(s, bx, top + th + Inches(0.3), bw, bh - th, bullets, 18)
        elif bullets:
            _bullets(s, bx, top, bw, bh, bullets, 22)
        note = sd.get("note")
        if note:
            _text(s, MARGIN, H - Inches(0.75), W - 2 * MARGIN - Inches(1), Inches(0.4), note, 11, False, MUTED)
        _text(s, W - MARGIN - Inches(1.5), H - Inches(0.6), Inches(1.5), Inches(0.35),
              f"{company + '   ' if company else ''}{idx} / {total}", 10, False, MUTED, PP_ALIGN.RIGHT)
        if sd.get("speaker_notes"):
            s.notes_slide.notes_text_frame.text = str(sd["speaker_notes"])

    path = _new_path(filename)
    prs.save(str(path))
    return path


def register(mcp) -> None:

    @mcp.tool()
    def ppt_presentation(filename: str, title: str, slides: list, subtitle: str = "", client: str = "") -> str:
        """Make a PowerPoint (.pptx, 16:9) for a customer: 제안서, 디자인 설명,
        시공 계획, 견적 요약. A cover slide (title/subtitle/client/사무소 정보)
        is added automatically. Saved as a NEW file in the open 현장's 결과물
        folder (or work\\결과물).

        slides: list of {"title": str,
                         "bullets": [str, ...]        (start a line with two spaces for a sub-point),
                         "image": "path.png",         (capture_view / sketchup_capture / 사진; relative = 결과물 folder)
                         "table": [[header...], [row...], ...],   (면적표, 견적 요약 — use numbers measured by tools)
                         "note": "small footnote",
                         "speaker_notes": "발표자 메모"}
        Image + bullets/table on one slide = image left, text right.
        Good flow: 표지 → 현장 개요 → 평면도(capture_view) → 3D(sketchup_capture) →
        실별 면적표 → 자재·마감 → 공정/일정 → 견적 요약 → 마무리.
        Numbers must come from tools (cad_room_areas, excel_estimate ...), never invented.
        """
        p = build_ppt(filename, title, slides, subtitle, client)
        return f"PPT를 만들었습니다: {p} (표지 포함 {len(slides) + 1}장)"
