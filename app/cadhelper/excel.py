"""Excel output: 견적서 (estimate with live formulas) and generic tables
(면적표, 물량표, 창호표 ...). Files go to the output folder; nothing existing is
overwritten -- a number is added to the name instead.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .learn import load_prices, load_profile
from .safety import HOME, OUT_DIR

THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="E9EEF2")
SUB_FILL = PatternFill("solid", fgColor="F6F7F8")
FONT = "맑은 고딕"
WON = '#,##0;[Red]-#,##0'


def _new_path(filename: str) -> Path:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(filename).stem or "표")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"{stem}.xlsx"
    n = 2
    while p.exists():
        p = OUT_DIR / f"{stem} ({n}).xlsx"
        n += 1
    return p


def _f(bold=False, size=10, color=None):
    return Font(name=FONT, bold=bold, size=size, color=color)


def build_estimate(filename, project, client, items, vat=True, overhead_pct=0.0,
                   profit_pct=0.0, note="", valid_days=30) -> tuple[Path, list[str]]:
    if not items:
        raise ValueError("견적 항목(items)이 비어 있습니다. 최소 한 줄은 있어야 합니다.")
    prof = load_profile()
    prices = load_prices()
    warnings = []
    wb = Workbook()
    ws = wb.active
    ws.title = "견적서"
    widths = [6, 16, 26, 22, 9, 7, 14, 16, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:I1")
    ws["A1"] = "견   적   서"
    ws["A1"].font = _f(True, 20)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 36

    info = [
        ("공사명", project), ("고객", f"{client} 귀하" if client else ""),
        ("견적일", date.today().isoformat()), ("유효기간", f"견적일로부터 {valid_days}일"),
    ]
    company = [
        ("상호", prof.get("company", "")), ("대표", prof.get("ceo", "")),
        ("연락처", prof.get("phone", "")), ("주소", prof.get("address", "")),
    ]
    for i, ((k1, v1), (k2, v2)) in enumerate(zip(info, company)):
        r = 3 + i
        ws.cell(r, 1, k1).font = _f(True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        ws.cell(r, 2, v1).font = _f()
        ws.cell(r, 6, k2).font = _f(True)
        ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=9)
        ws.cell(r, 7, v2).font = _f()
    if not prof.get("company"):
        warnings.append("회사 정보(상호·연락처)가 비어 있음 → learn_set_profile로 한 번 저장해 두면 다음부터 자동 입력")

    head_row = 9
    heads = ["No", "구분", "품명", "규격", "수량", "단위", "단가", "금액", "비고"]
    for c, h in enumerate(heads, 1):
        cell = ws.cell(head_row, c, h)
        cell.font = _f(True)
        cell.fill = HEAD_FILL
        cell.border = BOX
        cell.alignment = Alignment(horizontal="center", vertical="center")

    r = head_row + 1
    first = r
    cat_ranges: dict[str, list[int]] = {}
    for n, it in enumerate(items, 1):
        name = str(it.get("name", ""))
        price = it.get("unit_price")
        if price in (None, ""):
            hit = prices.get(f"{name}|{it.get('spec', '')}") or prices.get(name)
            if hit:
                price = hit["price"]
                it.setdefault("unit", hit.get("unit", ""))
                it["note"] = (it.get("note") or "") + (" " if it.get("note") else "") + "(저장된 단가)"
            else:
                price = 0
                warnings.append(f"'{name}' 단가 없음 → 0원으로 넣음. 아빠에게 단가를 물어보고 learn_set_prices로 저장할 것")
        row = [n, it.get("category", ""), name, it.get("spec", ""), float(it.get("qty") or 0),
               it.get("unit", ""), float(price or 0), None, it.get("note", "")]
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            cell.font = _f()
            cell.border = BOX
        ws.cell(r, 8, f"=E{r}*G{r}")
        ws.cell(r, 5).number_format = '#,##0.00'
        ws.cell(r, 7).number_format = WON
        ws.cell(r, 8).number_format = WON
        ws.cell(r, 1).alignment = Alignment(horizontal="center")
        cat_ranges.setdefault(str(it.get("category", "")), []).append(r)
        r += 1
    last = r - 1

    def total_line(label, formula, bold=False, fill=None):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        c = ws.cell(r, 1, label)
        c.font = _f(bold)
        c.alignment = Alignment(horizontal="right")
        v = ws.cell(r, 8, formula)
        v.font = _f(bold)
        v.number_format = WON
        for col in range(1, 10):
            ws.cell(r, col).border = BOX
            if fill:
                ws.cell(r, col).fill = fill
        row = r
        r += 1
        return row

    if len([k for k in cat_ranges if k]) > 1:
        for cat, rows in cat_ranges.items():
            refs = ",".join(f"H{x}" for x in rows)
            total_line(f"{cat or '기타'} 소계", f"=SUM({refs})", fill=SUB_FILL)
    direct = total_line("공사비 합계", f"=SUM(H{first}:H{last})", True)
    parts = [f"H{direct}"]
    if overhead_pct:
        parts.append(f"H{total_line(f'일반관리비 ({overhead_pct:g}%)', f'=ROUND(H{direct}*{overhead_pct/100},-1)')}")
    if profit_pct:
        parts.append(f"H{total_line(f'이윤 ({profit_pct:g}%)', f'=ROUND(H{direct}*{profit_pct/100},-1)')}")
    supply = total_line("공급가액", "=" + "+".join(parts), True)
    if vat:
        vat_row = total_line("부가세 (10%)", f"=ROUND(H{supply}*0.1,-1)")
        grand = total_line("총 견적금액 (VAT 포함)", f"=H{supply}+H{vat_row}", True, HEAD_FILL)
    else:
        grand = total_line("총 견적금액 (VAT 별도)", f"=H{supply}", True, HEAD_FILL)
    ws.cell(grand, 8).font = _f(True, 12)

    r += 1
    for line in [l for l in [note, prof.get("estimate_footer", "")] if l]:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
        ws.cell(r, 1, line).font = _f(size=9, color="555555")
        ws.cell(r, 1).alignment = Alignment(wrap_text=True)
        r += 1

    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{head_row}:{head_row}"
    ws.freeze_panes = ws.cell(head_row + 1, 1)
    path = _new_path(filename)
    wb.save(path)
    return path, warnings


def build_tables(filename, sheets) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for sh in sheets:
        ws = wb.create_sheet(re.sub(r'[\\/*?:\[\]]', "_", str(sh.get("name") or "표"))[:31])
        cols = sh.get("columns") or []
        rows = sh.get("rows") or []
        r = 1
        if sh.get("title"):
            ws.cell(1, 1, sh["title"]).font = _f(True, 14)
            r = 3
        for c, h in enumerate(cols, 1):
            cell = ws.cell(r, c, h)
            cell.font = _f(True)
            cell.fill = HEAD_FILL
            cell.border = BOX
            cell.alignment = Alignment(horizontal="center")
        start = r + 1
        for row in rows:
            r += 1
            for c, v in enumerate(row, 1):
                cell = ws.cell(r, c, v)
                cell.font = _f()
                cell.border = BOX
                if isinstance(v, (int, float)):
                    cell.number_format = '#,##0' if float(v).is_integer() else '#,##0.00'
        sum_cols = sh.get("sum_columns") or []
        if sum_cols and rows:
            r += 1
            ws.cell(r, 1, "합계").font = _f(True)
            for name in sum_cols:
                if name in cols:
                    ci = cols.index(name) + 1
                    L = get_column_letter(ci)
                    cell = ws.cell(r, ci, f"=SUM({L}{start}:{L}{r - 1})")
                    cell.font = _f(True)
                    cell.number_format = '#,##0.00'
            for c in range(1, len(cols) + 1):
                ws.cell(r, c).border = BOX
                ws.cell(r, c).fill = SUB_FILL
        for c in range(1, len(cols) + 1):
            values = [str(cols[c - 1])] + [str(rw[c - 1]) for rw in rows if len(rw) >= c]
            ws.column_dimensions[get_column_letter(c)].width = min(45, max(8, max(len(v) for v in values) * 1.6))
        ws.freeze_panes = ws.cell(start, 1)
    path = _new_path(filename)
    wb.save(path)
    return path


def register(mcp) -> None:

    @mcp.tool()
    def excel_estimate(filename: str, project: str, items: list, client: str = "",
                       vat: bool = True, overhead_pct: float = 0.0, profit_pct: float = 0.0,
                       note: str = "", valid_days: int = 30) -> str:
        """Make a 견적서 (estimate) .xlsx with live formulas (금액=수량×단가,
        구분별 소계, 합계, 관리비/이윤 optional, 부가세 10%, 총액), A4 print-ready.

        items: [{"category": "목공", "name": "석고보드", "spec": "9.5T 2겹",
                 "qty": 84.9, "unit": "㎡", "unit_price": 18000, "note": ""}, ...]
        Leave unit_price out to use the office's saved price list (learn_set_prices).
        Company name/phone come from the saved office profile (learn_set_profile).
        Quantities should come from cad_measure / cad_room_areas /
        sketchup_model_info -- say in "note" how they were measured.
        Creates a new file; never overwrites.
        """
        path, warnings = build_estimate(filename, project, client, items, vat, overhead_pct,
                                        profit_pct, note, valid_days)
        msg = f"견적서 생성: {path}"
        if warnings:
            msg += "\n확인 필요:\n- " + "\n- ".join(dict.fromkeys(warnings))
        return msg

    @mcp.tool()
    def excel_table(filename: str, sheets: list) -> str:
        """Write one or more tables to a new .xlsx (면적표, 물량표, 창호표, 자재표…).

        sheets: [{"name": "면적표", "title": "실별 면적표",
                  "columns": ["실명", "면적(㎡)", "평"],
                  "rows": [["거실", 32.5, 9.83], ...],
                  "sum_columns": ["면적(㎡)", "평"]}]
        Numbers must be numbers (not strings) so Excel can add them.
        """
        return f"엑셀 생성: {build_tables(filename, sheets)}"
