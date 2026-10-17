import json
from types import SimpleNamespace

from stream_translator_gpt import asr_postprocessor as asr


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def tokenize(self, text):
        self.calls.append(text)
        readings = {"水星": "スイセイ", "彗星": "スイセイ",
                    "姉ちゃん": "ネエチャン", "水ちゃん": "スイチャン"}
        return [SimpleNamespace(surface=text, reading=readings.get(text, "*"))]


def corrector(anchor):
    result = asr.ASRTermCorrector([{"canonical": anchor, "aliases": []}])
    result._reading_tokenizer = FakeTokenizer()
    return result


def test_homophone_and_anchor_cache():
    engine = corrector("彗星")
    suggestion = engine.suggest_aliases("水星")[0]
    assert suggestion["alias"] == "水星"
    assert suggestion["score"] == 1.0
    assert suggestion["reading_match"] is True
    engine.suggest_aliases("水星")
    assert engine._reading_tokenizer.calls.count("彗星") == 1
    assert engine._reading_tokenizer.calls.count("水星") == 2


def test_reading_rejects_surface_similarity():
    assert corrector("水ちゃん").suggest_aliases("姉ちゃん") == []


def test_unavailable_addon_uses_surface(monkeypatch, tmp_path):
    monkeypatch.setenv("STREAM_TRANSLATOR_READING_ADDON", str(tmp_path / "missing"))
    asr.configure_asr_correction_learning(True, tmp_path / "candidates.log", tmp_path / "summary.json")
    try:
        engine = asr.ASRTermCorrector([{"canonical": "水ちゃん"}])
        assert engine.suggest_aliases("姉ちゃん")[0]["reading_match"] is None
    finally:
        asr.configure_asr_correction_learning(False)


def test_summary_retains_homophone(monkeypatch, tmp_path):
    summary = tmp_path / "summary.json"
    asr.configure_asr_correction_learning(True, tmp_path / "candidates.log", summary)
    try:
        engine = corrector("彗星")
        asr.observe_asr_correction_candidate(engine, "水星")
        asr.observe_asr_correction_candidate(engine, "水星")
        record = json.loads(summary.read_text(encoding="utf-8"))["records"][0]
        assert record["reading_match"] is True
        assert record["count"] == 2
        engine._reading_tokenizer = None
        engine._reading_attempted = True
        monkeypatch.setattr(engine, "suggest_aliases", lambda text: [
            {"alias": "水星", "canonical": "彗星", "score": 0.9, "reading_match": None}])
        asr.observe_asr_correction_candidate(engine, "水星")
        assert json.loads(summary.read_text(encoding="utf-8"))["records"][0]["reading_match"] is True
    finally:
        asr.configure_asr_correction_learning(False)


def test_learning_off_never_loads_addon(monkeypatch):
    asr.configure_asr_correction_learning(False)
    engine = asr.ASRTermCorrector([{"canonical": "彗星"}])
    monkeypatch.setenv("STREAM_TRANSLATOR_READING_ADDON", "not-an-install")
    assert engine._get_reading_tokenizer() is None
    assert engine._reading_attempted is False


def test_clear_during_session_resets_existing_pair(tmp_path):
    from datetime import datetime, timezone
    summary = tmp_path / "summary.json"
    asr.configure_asr_correction_learning(True, tmp_path / "candidates.log", summary)
    try:
        engine = corrector("水星")
        asr.observe_asr_correction_candidate(engine, "彗星")
        asr.observe_asr_correction_candidate(engine, "彗星")
        assert json.loads(summary.read_text(encoding="utf-8"))["records"]
        cutoff = datetime.now(timezone.utc).isoformat()
        summary.write_text(json.dumps({"version": 2, "cleared_at": cutoff,
                                      "records": [], "pending_records": []}), encoding="utf-8")
        asr.observe_asr_correction_candidate(engine, "彗星")
        payload = json.loads(summary.read_text(encoding="utf-8"))
        assert payload["records"] == []
        assert payload["pending_records"][0]["count"] == 1
        assert payload["cleared_at"] == cutoff
        asr.observe_asr_correction_candidate(engine, "彗星")
        assert json.loads(summary.read_text(encoding="utf-8"))["records"][0]["count"] == 2
    finally:
        asr.configure_asr_correction_learning(False)


def test_short_present_anchor_does_not_suppress_reading_suggestion():
    engine = asr.ASRTermCorrector([{"canonical": "水星", "aliases": ["星"]}])
    engine._reading_tokenizer = FakeTokenizer()
    assert engine.suggest_aliases("彗星")[0]["canonical"] == "水星"
