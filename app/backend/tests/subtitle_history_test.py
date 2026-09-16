from subtitle_history import find_subtitle_index


def test_translation_update_merges_one_millisecond_timestamp_drift():
    lines = [{
        "timestamp": "00:02:10,015 -> 00:02:11,936",
        "original": "新たな未来",
        "translated": "",
    }]
    translated = {
        "timestamp": "00:02:10,016 -> 00:02:11,936",
        "segment_id": 23,
        "original": "新たな未来",
        "translated": "新的未來",
    }

    assert find_subtitle_index(lines, translated) == 0


def test_similar_timestamp_does_not_merge_different_text():
    lines = [{
        "timestamp": "00:02:10,015 -> 00:02:11,936",
        "original": "新たな未来",
    }]
    next_line = {
        "timestamp": "00:02:10,016 -> 00:02:11,936",
        "original": "別の文",
    }

    assert find_subtitle_index(lines, next_line) == -1


def test_same_text_outside_timestamp_tolerance_stays_separate():
    lines = [{
        "timestamp": "00:02:10,015 -> 00:02:11,936",
        "original": "新たな未来",
    }]
    repeated_later = {
        "timestamp": "00:02:10,100 -> 00:02:12,021",
        "original": "新たな未来",
    }

    assert find_subtitle_index(lines, repeated_later) == -1
