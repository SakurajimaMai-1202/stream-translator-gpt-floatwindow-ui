"""Compare explicit ASR and translation language selections."""

def same_language(source: str | None, target: str | None) -> bool:
    aliases = {
        'japanese': 'ja', '日文': 'ja', 'ja-jp': 'ja',
        'english': 'en', '英文': 'en', 'en-us': 'en', 'en-gb': 'en',
        'korean': 'ko', '韓文': 'ko', 'ko-kr': 'ko',
        'traditional chinese': 'zh-hant', '繁體中文': 'zh-hant', 'zh-tw': 'zh-hant',
        'simplified chinese': 'zh-hans', '簡體中文': 'zh-hans', 'zh-cn': 'zh-hans',
    }
    def normalize(value):
        value = str(value or '').strip().lower().replace('_', '-')
        return aliases.get(value, value)
    source, target = normalize(source), normalize(target)
    return bool(source and source != 'auto' and source == target)
