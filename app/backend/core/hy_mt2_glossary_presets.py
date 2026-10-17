"""Small, opt-in translation glossaries for common Japanese livestream topics."""

# Words local models keep in katakana. The マシュマロ variants are how ASR
# usually mishears it; Japanese viewers call レンタルスペース レンスペ.
_LIVESTREAM_TERMS = {
    "マシュマロ": "棉花糖",
    "コスプレ": "Cosplay",
    "チェキ": "拍立得",
    "レンタルスペース": "租借場地",
    "レンスペ": "租借場地",
    # Everyday chat words collected from real streams. Ambiguous ones such as
    # ポスト (post box), トマホーク (missile) or チャッピー (a common pet name)
    # are left to the model.
    "ノンデリ": "沒神經",
    "ハッシュタグ": "hashtag",
    "ツイート": "推文",
    "リツイート": "轉推",
    "お便り": "來信",
    "ふつおた": "普通來信",
    "メン限": "會員限定",
    "バーチャルアイドル": "虛擬偶像",
    "ポンポンペイン": "肚子痛",
    "アクアパッツァ": "義式水煮魚",
    "鯛の塩釜焼き": "鹽釜烤鯛魚",
    "塩釜焼き": "鹽釜燒",
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
        "ホロライブ": "Hololive",
        "ホロメン": "Hololive 成員",
        "ホロスターズ": "HOLOSTARS",
        "星街すいせい": "星街彗星",
        "白上フブキ": "白上吹雪",
        "さくらみこ": "櫻巫女",
        "兎田ぺこら": "兔田佩克拉",
        "猫又おかゆ": "貓又小粥",
        "宝鐘マリン": "寶鐘瑪琳",
    },
    "cosplay": {
        "コスプレイヤー": "Coser",
        "ウィッグ": "假髮",
        "カラコン": "變色隱形眼鏡",
        "衣装製作": "服裝製作",
        "撮影会": "攝影會",
        "宅コス": "居家 Cosplay",
        "コスイベ": "Cosplay 活動",
    },
}


def get_preset_terms(preset: str) -> dict[str, str]:
    return dict(PRESETS.get(preset, {}))


CATEGORY_LABELS = {
    "general_chat": "一般直播",
    "hololive_vtuber": "Hololive／VTuber",
    "cosplay": "Cosplay",
}


def active_user_terms(terminology: dict, categories) -> list[dict]:
    """Global rows precede rows in any selected category."""
    active = {categories} if isinstance(categories, str) else set(categories)
    rows = terminology.get("glossary_list", [])
    rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return ([row for row in rows if (row.get("scope") or "all") == "all"]
            + [row for row in rows if (row.get("scope") or "all") != "all" and row.get("scope") in active])


def effective_user_glossary(terminology: dict, categories) -> dict[str, str]:
    glossary = {}
    for row in active_user_terms(terminology, categories):
        source, target = row.get("original"), row.get("translated")
        if isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip():
            for name in [source.strip(), *_term_aliases(row)]:
                glossary[name] = target.strip()
    return glossary


# How ASR usually mishears the built-in terms; corrected before translation.
PRESET_ASR_VARIANTS: dict[str, dict[str, list[str]]] = {
    "general_chat": {
        "マシュマロ": ["マシュモロ", "マシモロ"],
        # No 面言 for メン限: substring correction corrupts 当面言わない.
        "ノンデリ": ["のんでり"],
        "バーチャルアイドル": ["バーチャルアイトル"],
    },
    "hololive_vtuber": {},
    "cosplay": {},
}
PRESET_ASR_VARIANTS_FLAT = frozenset(
    alias for variants in PRESET_ASR_VARIANTS.values()
    for aliases in variants.values() for alias in aliases
)

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
    if not isinstance(names, list):
        return []
    return list(dict.fromkeys(name.strip() for name in names if isinstance(name, str) and name.strip()))


def session_vocabulary(config: dict) -> dict:
    """Resolve all session feeds from the same categories and enabled rows."""
    terminology = config.get("terminology", {})
    categories = {"all", *terminology.get("active_categories", [])}
    user = terminology if terminology.get("use_terminology_glossary", True) else {}
    rows = active_user_terms(terminology, categories)
    disabled = {(item.get("category"), item.get("source"))
                for item in terminology.get("builtin_disabled", []) if isinstance(item, dict)}
    terms, variants = {}, {}
    for category, preset in PRESETS.items():
        if category not in categories:
            continue
        for source, target in preset.items():
            if (category, source) in disabled:
                continue
            terms[source] = target
            aliases = PRESET_ASR_VARIANTS.get(category, {}).get(source, [])
            if aliases:
                variants[source] = aliases
                terms.update({alias: target for alias in aliases})
    # A user row filed under a built-in category overrides that built-in term;
    # with an empty 譯法 it means "correct recognition only", so the built-in
    # translation must go too. Rows in other categories (e.g. migrated 一般
    # ASR-only rows) are not overrides.
    for row in active_user_terms(user, categories):
        source = str(row.get("original") or "").strip()
        category = row.get("scope") or "all"
        if (not str(row.get("translated") or "").strip() and source in PRESETS.get(category, {})
                and (category, source) not in disabled):
            for key in (source, *PRESET_ASR_VARIANTS.get(category, {}).get(source, [])):
                terms.pop(key, None)
    terms.update(effective_user_glossary(user, categories))
    originals = {str(row.get("original") or "").strip() for row in rows}
    originals.update(source for category in categories for source in PRESETS.get(category, {})
                     if (category, source) not in disabled)
    candidates = [(str(row.get("original") or "").strip(), _term_aliases(row)) for row in rows]
    candidates.extend(variants.items())

    def rewrites_a_correct_word(alias, canonical):
        # An alias inside its own original would double it (麻衣 → 桜島桜島麻衣).
        if alias in canonical:
            return True
        # Proper substrings can corrupt even ASR-only originals. Exact words
        # may be normalized only if their effective translations agree, or
        # the other original has no translation.
        return any(alias in original and (
                       alias != original or
                       (terms.get(original) and terms.get(original) != terms.get(canonical)))
                   for original in originals if original != canonical)

    rules = []
    for canonical, aliases in candidates:
        safe = [alias for alias in aliases if not rewrites_a_correct_word(alias, canonical)]
        if canonical and safe:
            rules.append({"canonical": canonical, "aliases": safe})
    misheard = {alias for _, aliases in candidates for alias in aliases}
    return {"translation_terms": terms, "asr_rules": rules, "active_categories": categories,
            "hotwords": glossary_hotwords(user, categories, misheard, max_chars=300)}


def glossary_asr_rules(terminology: dict, categories) -> list[dict]:
    active = [categories] if isinstance(categories, str) else list(categories)
    return session_vocabulary({"terminology": {**terminology, "active_categories": active}})["asr_rules"]


def glossary_hotwords(terminology: dict, preset, misheard=frozenset(), max_chars: int = 200) -> list[str]:
    """Glossary originals for ASR prompts: this scope's rows, then active global words.

    Some originals are themselves a misheard spelling kept for translation;
    anything in misheard must not be suggested to the ASR as the right word."""
    rows = active_user_terms(terminology, preset)
    scoped = [item for item in rows if (item.get("scope") or "all") != "all"]
    ordered = [item.get("original") for item in scoped + [item for item in rows if item not in scoped]]
    words, used = [], 0
    for word in dict.fromkeys(str(value or "").strip() for value in ordered):
        if not word or any(char in word for char in ",，、") or word in PRESET_ASR_VARIANTS_FLAT or word in misheard:
            continue
        if used + len(word) + 2 > max_chars:
            break
        words.append(word)
        used += len(word) + 2
    return words

