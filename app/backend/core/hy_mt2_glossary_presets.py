"""Small, opt-in translation glossaries for common Japanese livestream topics."""

# Words local models keep in katakana. The マシュマロ variants are how ASR
# usually mishears it; Japanese viewers call レンタルスペース レンスペ.
_LIVESTREAM_TERMS = {
    "マシュマロ": "棉花糖",
    "マシュモロ": "棉花糖",
    "マシモロ": "棉花糖",
    "コスプレ": "Cosplay",
    "チェキ": "拍立得",
    "レンタルスペース": "租借場地",
    "レンスペ": "租借場地",
}

PRESETS: dict[str, dict[str, str]] = {
    "general_chat": {
        **_LIVESTREAM_TERMS,
        "雑談配信": "雜談直播",
        "コラボ配信": "連動直播",
        "切り抜き": "精華片段",
        "同時視聴": "同步觀看",
        "推し活": "推活",
        "初見さん": "第一次來看的觀眾",
        "スパチャ": "SC 贊助",
    },
    "hololive_vtuber": {
        **_LIVESTREAM_TERMS,
        "ホロライブ": "Hololive",
        "ホロメン": "Hololive 成員",
        "ホロスターズ": "HOLOSTARS",
        "星街すいせい": "星街彗星",
        "白上フブキ": "白上吹雪",
        "さくらみこ": "櫻巫女",
        "兎田ぺこら": "兔田佩克拉",
        "猫又おかゆ": "貓又小粥",
        "宝鐘マリン": "寶鐘瑪琳",
        "雑談配信": "雜談直播",
        "コラボ配信": "連動直播",
        "切り抜き": "精華片段",
        "同時視聴": "同步觀看",
        "推し活": "推活",
        "スパチャ": "SC 贊助",
    },
    "cosplay": {
        **_LIVESTREAM_TERMS,
        "コスプレ": "Cosplay",
        "コスプレイヤー": "Coser",
        "ウィッグ": "假髮",
        "カラコン": "變色隱形眼鏡",
        "衣装製作": "服裝製作",
        "撮影会": "攝影會",
        "宅コス": "居家 Cosplay",
        "コスイベ": "Cosplay 活動",
        "雑談配信": "雜談直播",
        "コラボ配信": "連動直播",
        "切り抜き": "精華片段",
    },
}


def get_preset_terms(preset: str) -> dict[str, str]:
    return dict(PRESETS.get(preset, {}))


def active_user_terms(terminology: dict, preset: str) -> list[dict]:
    """Keep legacy unscoped rows global; apply scoped rows only in their profile."""
    rows = terminology.get("glossary_list", [])
    if not isinstance(rows, list):
        return []
    global_rows = [item for item in rows if isinstance(item, dict) and str(item.get("scope") or "all") == "all"]
    scoped_rows = [item for item in rows if isinstance(item, dict) and preset and preset != "all" and item.get("scope") == preset]
    return global_rows + scoped_rows


def effective_user_glossary(terminology: dict, preset: str) -> dict[str, str]:
    # Preserve legacy precedence: when this old dictionary exists, it is the
    # active user glossary and glossary_list supplies aliases only.
    legacy = terminology.get("terminology_glossary") or {}
    if isinstance(legacy, dict) and legacy:
        return dict(legacy)
    glossary: dict[str, str] = {}
    for item in active_user_terms(terminology, preset):
        source, target = item.get("original"), item.get("translated")
        if isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip():
            glossary[source.strip()] = target.strip()
    return glossary


# How ASR usually mishears the built-in terms; corrected before translation.
PRESET_ASR_VARIANTS: dict[str, list[str]] = {
    "マシュマロ": ["マシュモロ", "マシモロ"],
}
PRESET_ASR_VARIANTS_FLAT = frozenset(alias for aliases in PRESET_ASR_VARIANTS.values() for alias in aliases)

# Backends that get glossary words as a prompt. SenseVoice and Parakeet have
# no prompt input. Qwen3-ASR does, but on singing, noise or silence it copies
# its context out as the transcript (see qwen3_context in config_manager), so
# like the others it relies on corrections instead.
ASR_PROMPT_BACKENDS = frozenset({
    "whisper", "faster-whisper", "faster-whisper-simul", "simul-streaming",
    "openai-api", "fun-asr-nano",
})


def _term_aliases(item: dict) -> list[str]:
    names = item.get("aliases") or []
    if isinstance(names, str):
        names = names.split(",")
    return [name.strip() for name in names if isinstance(name, str) and name.strip()]


def glossary_asr_rules(terminology: dict, preset: str) -> list[dict]:
    """Turn glossary aliases into ASR corrections toward the glossary original."""
    rules = []
    rows = active_user_terms(terminology, preset)
    originals = {str(item.get("original") or "").strip() for item in rows}
    for item in rows:
        original = str(item.get("original") or "").strip()
        # An alias inside any original (its own or another row's) would rewrite that correct word.
        aliases = [alias for alias in _term_aliases(item) if not any(alias in name for name in originals)]
        if original and aliases:
            rules.append({"canonical": original, "aliases": aliases})
    terms = PRESETS.get(preset, {})
    for canonical, aliases in PRESET_ASR_VARIANTS.items():
        if canonical in terms:
            rules.append({"canonical": canonical, "aliases": list(aliases)})
    return rules


def glossary_hotwords(terminology: dict, preset: str, misheard=frozenset(), max_chars: int = 200) -> list[str]:
    """Glossary originals for ASR prompts: this scope's rows, then active global words.

    Some originals are themselves a misheard spelling kept for translation;
    anything in misheard must not be suggested to the ASR as the right word."""
    rows = active_user_terms(terminology, preset)
    scoped = [item for item in rows if preset and item.get("scope") == preset]
    ordered = [item.get("original") for item in scoped + [item for item in rows if item not in scoped]]
    legacy = terminology.get("terminology_glossary") or {}
    if isinstance(legacy, dict) and legacy:
        ordered = [item.get("original") for item in scoped] + list(legacy)
    words, used = [], 0
    for word in dict.fromkeys(str(value or "").strip() for value in ordered):
        if not word or any(char in word for char in ",，、") or word in PRESET_ASR_VARIANTS_FLAT or word in misheard:
            continue
        if used + len(word) + 2 > max_chars:
            break
        words.append(word)
        used += len(word) + 2
    return words

