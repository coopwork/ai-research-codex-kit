#!/usr/bin/env python3
"""Conservative, OFFLINE structural QA for a Codex research run.

Passing this tool does not establish factual accuracy, peer review, or that
external integrations took place. Those must be independently inspected.
"""
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone

REF_PATTERN = re.compile(r"\[S\d{3,}\]")
SID_PATTERN = re.compile(r"S\d{3,}")
CID_PATTERN = re.compile(r"C\d{3,}")
SUPPORTED = {"supported", "partial", "unsupported", "contradicted"}
STATUSES = {"DONE", "NEEDS_USER_ACTION", "BLOCKED", "NOT_AVAILABLE"}


def assess(run: Path):
    errors, warnings, checks = [], [], []

    def problem(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    def read_json(filename):
        path = run / filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problem(f"{filename}: не читается JSON: {exc}")
            return {}

    def read_doc(filename, min_size=20):
        path = run / filename
        try:
            data = path.read_text(encoding="utf-8")
        except OSError:
            problem(f"Нет файла {filename}")
            return ""
        if len(data.strip()) < min_size:
            problem(f"{filename}: файл слишком короткий/пустой")
        return data

    run_cfg = read_json("run_config.json")
    min_sources = run_cfg.get("min_sources", 5)
    if not isinstance(min_sources, int) or min_sources < 1:
        problem("run_config.json: min_sources должно быть положительным целым")
        min_sources = 5
    for req in ("research_brief.md", "search_protocol.md", "search_log.md", "evidence_matrix.md", "outline.md", "tool_log.md", "summary.md"):
        read_doc(req)
    references = read_doc("references.md")
    draft = read_doc("draft.md", 80)
    source_data = read_json("sources.json")
    claim_data = read_json("claims.json")
    mapping_data = read_json("draft_claim_map.json")
    tool_statuses = read_json("tool_status.json")

    sources = source_data.get("sources", [])
    if not isinstance(sources, list):
        problem("sources.json: sources должен быть массивом")
        sources = []
    if len(sources) < min_sources:
        problem(f"Количество источников {len(sources)} меньше min_sources={min_sources}")
    source_by_id = {}
    for src in sources:
        if not isinstance(src, dict):
            problem("sources.json: элемент должен быть объектом")
            continue
        sid = src.get("id", "")
        if not SID_PATTERN.fullmatch(sid):
            problem(f"Некорректный Source ID: {sid!r}")
        if sid in source_by_id:
            problem(f"Дублирующийся Source ID: {sid}")
        source_by_id[sid] = src
        for key in ("title", "authors", "year", "url", "access_level", "metadata_status", "retraction_status"):
            if not src.get(key):
                problem(f"{sid}: отсутствует {key}")
        if src.get("metadata_status") != "verified":
            warn(f"{sid}: метаданные не отмечены как независимо проверенные")
        else:
            if not src.get("metadata_evidence_url") or not src.get("metadata_checked_at"):
                problem(f"{sid}: verified требует metadata_evidence_url и metadata_checked_at")
        if src.get("access_level") not in {"metadata_only", "abstract_only", "full_text"}:
            problem(f"{sid}: недопустимый access_level")
        if src.get("access_level") == "full_text" and not (src.get("full_text_path") or src.get("full_text_url")):
            problem(f"{sid}: full_text требует full_text_path или full_text_url")
        if src.get("retraction_status") == "flagged":
            problem(f"{sid}: ретракция/предупреждение отмечено flagged, требует отдельного решения")
        elif src.get("retraction_status") == "unknown":
            warn(f"{sid}: статус ретракции не проверен")

    claims = claim_data.get("claims", [])
    if not isinstance(claims, list):
        problem("claims.json: claims должен быть массивом")
        claims = []
    claim_by_id = {}
    for claim in claims:
        if not isinstance(claim, dict):
            problem("claims.json: элемент должен быть объектом")
            continue
        cid = claim.get("id", "")
        if not CID_PATTERN.fullmatch(cid):
            problem(f"Некорректный Claim ID: {cid!r}")
        if cid in claim_by_id:
            problem(f"Дублирующийся Claim ID: {cid}")
        claim_by_id[cid] = claim
        if claim.get("status") not in SUPPORTED:
            problem(f"{cid}: недопустимый статус поддержки")
        if not claim.get("text"):
            problem(f"{cid}: пустое утверждение")
        for sid in claim.get("source_ids", []):
            if sid not in source_by_id:
                problem(f"{cid}: неизвестный источник {sid}")
        if claim.get("status") == "supported":
            evidences = claim.get("evidence", [])
            if not evidences:
                problem(f"{cid}: supported без массива evidence")
            for ev in evidences:
                sid = ev.get("source_id", "")
                if sid not in claim.get("source_ids", []):
                    problem(f"{cid}: evidence {sid} не входит в source_ids")
                if not ev.get("locator") or not ev.get("evidence_excerpt"):
                    problem(f"{cid}: у evidence {sid} отсутствует locator/excerpt")
                if ev.get("verification_level") not in {"abstract_only", "full_text"}:
                    problem(f"{cid}: evidence должен иметь verification_level")
                sr = source_by_id.get(sid, {})
                if sr.get("access_level") == "metadata_only":
                    problem(f"{cid}: {sid} metadata_only не подтверждает научный тезис")
                if ev.get("verification_level") == "full_text" and sr.get("access_level") != "full_text":
                    problem(f"{cid}: full_text-верификация невозможна при доступе {sr.get('access_level')}")
                if ev.get("verified_against_original") is not True:
                    warn(f"{cid}: {sid} не отмечен как перепроверенный по оригиналу")
        if claim.get("include_in_draft", False) and claim.get("status") != "supported":
            problem(f"{cid}: включение в draft разрешено только для supported")

    mappings = mapping_data.get("mappings", [])
    if not isinstance(mappings, list):
        problem("draft_claim_map.json: mappings должен быть массивом")
        mappings = []
    mapped_ids = []
    for m in mappings:
        cid = m.get("claim_id", "")
        mapped_ids.append(cid)
        if cid not in claim_by_id:
            problem(f"draft_claim_map: неизвестный {cid}")
            continue
        claim = claim_by_id[cid]
        if not claim.get("include_in_draft", False):
            problem(f"{cid}: есть в draft_claim_map, но include_in_draft=false")
        excerpt = m.get("draft_excerpt", "")
        if len(excerpt) < 15 or excerpt not in draft:
            problem(f"{cid}: точный фрагмент draft_excerpt отсутствует в draft.md или слишком короткий")
            continue
        paragraph = next((p for p in re.split(r"\n\s*\n", draft) if excerpt in p), "")
        mids = m.get("source_ids", [])
        if not mids:
            problem(f"{cid}: в mapping не указаны источники")
        for sid in mids:
            if sid not in claim.get("source_ids", []):
                problem(f"{cid}: источник {sid} не поддерживает claim")
            if f"[{sid}]" not in paragraph:
                problem(f"{cid}: в абзаце нет [{sid}]")
        if not any(e.get("source_id") in mids for e in claim.get("evidence", [])):
            problem(f"{cid}: ни одна evidence не связана с цитатой в тексте")
    for cid, claim in claim_by_id.items():
        if claim.get("include_in_draft", False) and cid not in mapped_ids:
            problem(f"{cid}: включён в черновик, но отсутствует в draft_claim_map")
    for ref in REF_PATTERN.findall(draft):
        sid = ref[1:-1]
        if ref not in references:
            problem(f"references.md: отсутствует библиографическая запись для {ref}")
        if sid in source_by_id and source_by_id[sid].get("access_level") == "abstract_only":
            warn(f"draft.md: {ref} проверен только по аннотации, не по полному тексту")
        if sid not in source_by_id:
            problem(f"draft.md: ссылка {ref} на отсутствующий источник")
        elif source_by_id[sid].get("metadata_status") != "verified":
            problem(f"draft.md: ссылка {ref} на источник без проверенных метаданных")
    if not REF_PATTERN.search(draft):
        problem("draft.md: нет ссылок [S001] на источники")
    if len(set(mapped_ids)) != len(mapped_ids):
        problem("Повторение claim_id в draft_claim_map")

    for key in ("scholar", "notebooklm", "independent_fact_check"):
        value = tool_statuses.get(key, {})
        status = value.get("status") if isinstance(value, dict) else None
        if status not in STATUSES:
            problem(f"tool_status.json: {key} имеет недопустимый/отсутствующий статус")
        elif status == "DONE" and not value.get("evidence"):
            problem(f"tool_status.json: {key} DONE без evidence (URL/журнал действий)")
        elif status != "DONE":
            warn(f"{key}: статус {status}; полный автоматический проход не подтверждён")

    if not claims:
        problem("Нет записанных тезисов в claims.json")
    if not mappings:
        problem("Нет связей тезисов с черновиком в draft_claim_map.json")

    checks.append("OFFLINE_SCHEMA_AND_CITATION_CHECK_ONLY: scientific correctness not verified")
    status = "FAIL" if errors else "PASS_WITH_LIMITATIONS" if warnings else "PASS_STRUCTURAL_ONLY"
    report = {"status": status, "at_utc": datetime.now(timezone.utc).isoformat(), "errors": errors,
              "warnings": warnings, "checks": checks, "source_count": len(sources),
              "claim_count": len(claims), "draft_citations": len(REF_PATTERN.findall(draft))}
    return report


def write_report(run: Path, report):
    run.mkdir(parents=True, exist_ok=True)
    (run / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    content = [f"# QA: {report['status']}", "", "Важно: проверка структурная и офлайн; результаты не являются независимой научной верификацией.", "",
               f"Источников: {report['source_count']}; тезисов: {report['claim_count']}; ссылок в тексте: {report['draft_citations']}.",
               "", "## Ошибки"]
    content += ["- " + e for e in report["errors"]] or ["- Нет"]
    content += ["", "## Предупреждения"]
    content += ["- " + w for w in report["warnings"]] or ["- Нет"]
    content += ["", "## Граница проверки", "- " + report["checks"][0], ""]
    (run / "qa_report.md").write_text("\n".join(content), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Offline research structural/citation QA")
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    report = assess(args.run)
    write_report(args.run, report)
    print(json.dumps({"status": report["status"], "errors": len(report["errors"]),
                      "warnings": len(report["warnings"]), "report": str(args.run / 'qa_report.md')}, ensure_ascii=False))
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
