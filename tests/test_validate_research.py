import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_research import assess, write_report  # noqa: E402


class ValidateResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "research"
        self.run.mkdir()
        for path in (ROOT / "templates").iterdir():
            if path.is_file():
                shutil.copyfile(path, self.run / path.name)
        for name in ("research_brief.md", "search_protocol.md", "search_log.md", "evidence_matrix.md",
                     "outline.md", "references.md", "tool_log.md", "summary.md"):
            (self.run / name).write_text("Тестовый файл с достаточно подробным описанием проверенных процедур и результата.", encoding="utf-8")
        self.save("run_config.json", {"min_sources": 2, "academic_style": "APA7"})
        self.save("sources.json", {"sources": [
            self.source("S001"), self.source("S002")
        ]})
        self.save("claims.json", {"claims": [{
            "id": "C001", "text": "Sample supported claim", "status": "supported",
            "include_in_draft": True, "source_ids": ["S001"],
            "evidence": [{"source_id": "S001", "locator": "Section 3, table 1",
                          "evidence_excerpt": "Exactly as confirmed by text", "verification_level": "full_text",
                          "verified_against_original": True}]
        }]})
        sentence = "В этом тестовом исследовании описана связь между факторами."
        (self.run / "references.md").write_text("[S001] А. Автор. Вымышленная тестовая запись (только для тестов).", encoding="utf-8")
        (self.run / "draft.md").write_text("# Обзор\n\n" + sentence + " [S001] Эта фраза иллюстрирует формат ссылки и достаточную длину.\n", encoding="utf-8")
        self.save("draft_claim_map.json", {"mappings": [{
            "claim_id": "C001", "draft_excerpt": sentence, "source_ids": ["S001"]
        }]})

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, id):
        return {"id": id, "title": f"Document {id}", "authors": ["A. Author"],
                "year": 2025, "url": f"https://example.org/{id}", "doi": f"10.5555/{id}",
                "metadata_status": "verified", "metadata_evidence_url": "https://api.crossref.org/works/10.5555",
                "metadata_checked_at": "2026-10-12", "access_level": "full_text",
                "full_text_url": f"https://example.org/{id}.pdf", "retraction_status": "screened_clear"}

    def save(self, name, data):
        (self.run / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_valid_fixture_is_structurally_valid(self):
        report = assess(self.run)
        self.assertFalse(report["errors"], report["errors"])
        self.assertEqual(report["status"], "PASS_WITH_LIMITATIONS")
        write_report(self.run, report)
        self.assertTrue((self.run / "qa_report.md").exists())

    def test_invented_draft_reference_fails(self):
        with (self.run / "draft.md").open("a", encoding="utf-8") as f:
            f.write("Некорректная ссылка [S999].\n")
        report = assess(self.run)
        self.assertTrue(any("отсутствующий источник" in e for e in report["errors"]))

    def test_claim_without_evidence_fails(self):
        data = json.loads((self.run / "claims.json").read_text(encoding="utf-8"))
        data["claims"][0]["evidence"] = []
        self.save("claims.json", data)
        report = assess(self.run)
        self.assertTrue(any("без массива evidence" in e for e in report["errors"]))

    def test_metadata_only_does_not_support_claim(self):
        data = json.loads((self.run / "sources.json").read_text(encoding="utf-8"))
        data["sources"][0]["access_level"] = "metadata_only"
        self.save("sources.json", data)
        report = assess(self.run)
        self.assertTrue(any("metadata_only не подтверждает" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
