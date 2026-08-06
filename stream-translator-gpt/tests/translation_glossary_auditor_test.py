import json
from types import SimpleNamespace

from stream_translator_gpt.translation_glossary_auditor import TranslationGlossaryAuditor


def _task(source, translation, segment_id=1):
    return SimpleNamespace(
        segment_id=segment_id,
        time_range=(1.0, 2.0),
        transcript=source,
        translation=translation,
        translation_provider="openai_compatible",
        translation_model="Tencent-Hunyuan/Hy-MT2",
    )


def test_audit_logs_compliance_without_creating_issue(tmp_path):
    log_path = tmp_path / "audit.log"
    issues_path = tmp_path / "issues.json"
    auditor = TranslationGlossaryAuditor(
        {"すいせいさん": "Suisei醬"}, True, log_path, issues_path,
    )

    results = auditor.audit(_task("すいせいさんです", "這是 Suisei醬"))

    assert results[0]["compliant"] is True
    assert json.loads(log_path.read_text(encoding="utf-8"))["source_term"] == "すいせいさん"
    assert json.loads(issues_path.read_text(encoding="utf-8"))["records"] == []


def test_repeated_missing_term_moves_from_pending_to_records(tmp_path):
    issues_path = tmp_path / "issues.json"
    auditor = TranslationGlossaryAuditor(
        {"スイちゃん": "Suisei醬"}, True, tmp_path / "audit.log", issues_path,
    )

    auditor.audit(_task("スイちゃんです", "她來了", 1))
    first = json.loads(issues_path.read_text(encoding="utf-8"))
    assert first["records"] == []
    assert first["pending_records"][0]["count"] == 1

    auditor.audit(_task("スイちゃんだ", "她來啦", 2))
    second = json.loads(issues_path.read_text(encoding="utf-8"))
    assert second["pending_records"] == []
    assert second["records"][0]["count"] == 2
    assert second["records"][0]["models"] == ["Tencent-Hunyuan/Hy-MT2"]


def test_nfkc_case_and_whitespace_matching(tmp_path):
    auditor = TranslationGlossaryAuditor(
        {"ＦＰＳ": "Frame Rate"}, True, tmp_path / "audit.log", tmp_path / "issues.json",
    )
    result = auditor.audit(_task("fps が低い", "FRAME   RATE 很低"))
    assert result[0]["compliant"] is True


def test_disabled_or_unmentioned_terms_do_not_write(tmp_path):
    log_path = tmp_path / "audit.log"
    disabled = TranslationGlossaryAuditor({"CPU": "處理器"}, False, log_path, tmp_path / "issues.json")
    assert disabled.audit(_task("CPU", "中央處理器")) == []
    assert not log_path.exists()

    enabled = TranslationGlossaryAuditor({"CPU": "處理器"}, True, log_path, tmp_path / "issues.json")
    assert enabled.audit(_task("GPU", "顯示卡")) == []
    assert not log_path.exists()
