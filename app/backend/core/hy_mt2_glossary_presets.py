"""Small, opt-in translation glossaries for common Japanese livestream topics."""

PRESETS: dict[str, dict[str, str]] = {
    "general_chat": {
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
        "雑談配信": "雜談直播",
        "コラボ配信": "連動直播",
        "切り抜き": "精華片段",
        "同時視聴": "同步觀看",
        "推し活": "推活",
        "スパチャ": "SC 贊助",
    },
    "cosplay": {
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
    scoped_rows = [item for item in rows if isinstance(item, dict) and preset and item.get("scope") == preset]
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
