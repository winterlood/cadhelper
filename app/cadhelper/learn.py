"""Memory that makes the helper better with use.

knowledge/profile.json   office info (회사명, 연락처, 견적서 하단 문구, 레이어 규칙…)
knowledge/prices.json    unit price list used to fill estimates
knowledge/lessons.md     corrections and preferences, one dated line each
~/.codex/skills/ch-learned-*/SKILL.md   procedures learned from repeated requests

Written through MCP tools so it works even when Codex's own sandbox cannot
write outside the project folder.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from .safety import HOME

KDIR = HOME / "knowledge"
PROFILE = KDIR / "profile.json"
PRICES = KDIR / "prices.json"
LESSONS = KDIR / "lessons.md"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
SKILLS_DIR = CODEX_HOME / "skills"
LEARNED_PREFIX = "ch-learned-"


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return default


def _write_json(p: Path, data) -> None:
    KDIR.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def load_profile() -> dict:
    return _read_json(PROFILE, {})


def load_prices() -> dict:
    return _read_json(PRICES, {})


def learned_skills() -> list[tuple[str, str]]:
    out = []
    if SKILLS_DIR.exists():
        for d in sorted(SKILLS_DIR.glob(LEARNED_PREFIX + "*")):
            f = d / "SKILL.md"
            if f.exists():
                m = re.search(r"^description:\s*(.+)$", f.read_text(encoding="utf-8-sig"), re.M)
                desc = m.group(1).strip() if m else ""
                if desc.startswith('"'):
                    try:
                        desc = json.loads(desc)
                    except Exception:  # noqa: BLE001
                        pass
                out.append((d.name, desc))
    return out


def register(mcp) -> None:

    @mcp.tool()
    def learn_read() -> str:
        """Read everything learned so far: office profile, saved prices,
        lessons/corrections, and learned skills. Call this at the START of
        every new conversation before doing any CAD/SketchUp/estimate work.
        """
        prof = load_profile()
        prices = load_prices()
        lessons = LESSONS.read_text(encoding="utf-8").strip() if LESSONS.exists() else ""
        skills = learned_skills()
        out = ["[사무소 정보]", json.dumps(prof, ensure_ascii=False, indent=1) if prof else "(아직 없음)",
               f"\n[저장된 단가] {len(prices)}개"]
        for k, v in list(prices.items())[:200]:
            out.append(f"- {k}: {v.get('price'):,}원/{v.get('unit', '')}  ({v.get('updated', '')})")
        out.append("\n[배운 점 / 고쳐준 것]")
        out.append(lessons[-6000:] if lessons else "(아직 없음)")
        out.append("\n[학습된 스킬]")
        out += [f"- {n}: {d}" for n, d in skills] or ["(아직 없음)"]
        return "\n".join(out)

    @mcp.tool()
    def learn_note(category: str, lesson: str) -> str:
        """Save one lesson so the same mistake never happens again.

        Call it whenever the user corrects you, states a preference, explains
        office jargon, or says how they like things done. category: one of
        규칙, 실수, 선호, 용어, 도면관례. lesson: one clear Korean sentence that
        will make sense months later (include layer names, numbers, file names).
        """
        KDIR.mkdir(parents=True, exist_ok=True)
        line = f"- [{date.today().isoformat()}][{category}] {lesson.strip()}\n"
        with LESSONS.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return "기억했습니다: " + line.strip()

    @mcp.tool()
    def learn_set_profile(fields: dict) -> str:
        """Save office info used on documents (merged into what is saved).
        Keys commonly used: company, ceo, phone, address, business_no, email,
        estimate_footer (견적서 하단 문구), default_wall_height_mm, layer_rules.
        """
        prof = load_profile()
        prof.update({k: v for k, v in fields.items() if v is not None})
        _write_json(PROFILE, prof)
        return "사무소 정보 저장: " + ", ".join(fields)

    @mcp.tool()
    def learn_set_prices(items: list) -> str:
        """Save or update unit prices for estimates.
        items: [{"name": "강마루", "spec": "", "unit": "㎡", "price": 65000}, ...]
        A spec makes a separate entry ("name|spec") for the same name.
        Only save prices the user actually told you.
        """
        prices = load_prices()
        for it in items:
            key = it["name"] if not it.get("spec") else f"{it['name']}|{it['spec']}"
            prices[key] = {"unit": it.get("unit", ""), "price": float(it["price"]),
                           "updated": date.today().isoformat()}
        _write_json(PRICES, prices)
        return f"단가 {len(items)}건 저장 (전체 {len(prices)}건)"

    @mcp.tool()
    def learn_save_skill(name: str, description: str, instructions: str) -> str:
        """Save a reusable procedure as a Codex skill (ch-learned-<name>).

        Do this when a kind of request has come up twice, or right after a
        multi-step job finally worked after corrections. name: short English
        slug (e.g. "room-area-excel"). description: one line saying WHEN to use
        it (Korean ok). instructions: the exact steps, tool names, layer names,
        pitfalls and checks that worked. Saving again with the same name
        updates it. Codex picks up new skills in the next conversation.
        """
        slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:48] or "skill"
        d = SKILLS_DIR / f"{LEARNED_PREFIX}{slug}"
        d.mkdir(parents=True, exist_ok=True)
        desc = " ".join(description.split())[:300]
        body = (f"---\nname: {LEARNED_PREFIX}{slug}\ndescription: {json.dumps(desc, ensure_ascii=False)}\n---\n\n"
                f"# {desc}\n\n(CAD도우미가 실제 작업에서 배워 저장한 절차. 마지막 수정 {date.today().isoformat()})\n\n"
                f"{instructions.strip()}\n")
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        with (KDIR / "skills_log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"- [{date.today().isoformat()}] {d.name}: {desc}\n")
        return f"스킬 저장: {d / 'SKILL.md'} (다음 대화부터 자동 적용)"
