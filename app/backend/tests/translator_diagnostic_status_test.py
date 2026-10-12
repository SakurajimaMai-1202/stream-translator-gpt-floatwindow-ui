from backend.core.translator import _diagnostic_status


def test_warning_and_error_status_payloads_and_rate_limit():
    recent = {}
    warning = _diagnostic_status('[WARNING] 字幕檔案無法寫入', recent, 100, [])
    assert warning == {'type': 'status', 'data': {'message': '字幕檔案無法寫入', 'level': 'warning'}}
    assert _diagnostic_status('[WARNING] 字幕檔案無法寫入', recent, 129.9, []) is None
    error = _diagnostic_status('[ERROR] 串流設定錯誤', recent, 101, [])
    assert error == {'type': 'status', 'data': {'message': '串流設定錯誤', 'level': 'error'}}
    assert _diagnostic_status('[ERROR] 串流設定錯誤', recent, 102, []) is None
    assert _diagnostic_status('[WARNING] 字幕檔案無法寫入', recent, 130, []) == warning


def test_info_debug_and_subtitles_are_not_diagnostic_statuses():
    for line in ('[INFO] Loading model', '[DEBUG] details', 'subtitle [WARNING] text'):
        assert _diagnostic_status(line, {}, 100, []) is None


def test_diagnostics_redact_command_secrets_and_signed_urls():
    event = _diagnostic_status(
        '[WARNING] failed abc-secret https://example.com/?token=private', {}, 100,
        ['python', '--openai_api_key', 'abc-secret'])
    assert event['data']['message'] == 'failed <redacted> <redacted-url>'
    for text in ('Cookie: session=private', 'Authorization: Bearer private',
                 'token=private', '"token": "private"', '--google_api_key private'):
        event = _diagnostic_status('[ERROR] ' + text, {}, 100, [])
        assert 'private' not in event['data']['message']


def test_distinct_warnings_and_levels_are_not_suppressed():
    recent = {}
    assert _diagnostic_status('[WARNING] first', recent, 0, [])
    assert _diagnostic_status('[WARNING] second', recent, 1, [])
    assert _diagnostic_status('[ERROR] first', recent, 2, [])
