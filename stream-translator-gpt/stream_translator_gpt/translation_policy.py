from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TranslationCapabilities:
    model_family: str
    supports_system_prompt: bool
    supports_structured_output: bool
    preferred_output_format: str
    default_max_concurrency: int
    temperature: float
    top_p: float
    top_k: int | None = None
    repetition_penalty: float | None = None


@dataclass(frozen=True)
class TranslationRequest:
    segment_id: int
    source_text: str
    previous_original: str = ""
    previous_translation: str = ""
    glossary: dict[str, str] | None = None
    previous_sources: tuple[str, ...] = ()
    source_language: str = "auto"
    target_language: str = "Traditional Chinese"
    candidates: dict[str, str] | None = None
    preserve_elements: tuple[str, ...] = ()
    repair: bool = False
    session_id: int = 0
    residual_kana: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedPrompt:
    system_instruction: str | None
    user_content: str
    output_format: str
    temperature: float
    top_p: float
    top_k: int | None
    repetition_penalty: float | None


@dataclass
class TranslationResult:
    segment_id: int
    translation: str = ""
    provider: str = ""
    model: str = ""
    queue_latency_ms: float | None = None
    generation_latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None
    validation_reasons: tuple[str, ...] = ()
    matched_terms: dict[str, str] | None = None
    retry_count: int = 0
    translation_kana_fallback: bool = False


_CAPABILITY_PRESETS = {
    "index_translate": TranslationCapabilities(
        model_family="index_translate", supports_system_prompt=False,
        supports_structured_output=False, preferred_output_format="text",
        default_max_concurrency=1, temperature=0.0, top_p=1.0,
    ),
    "hy_mt2": TranslationCapabilities(
        model_family="hy_mt2",
        supports_system_prompt=False,
        supports_structured_output=False,
        preferred_output_format="text",
        default_max_concurrency=1,
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
    ),
    "generic_chat": TranslationCapabilities(
        model_family="generic_chat",
        supports_system_prompt=True,
        supports_structured_output=False,
        preferred_output_format="text",
        default_max_concurrency=1,
        temperature=0.0,
        top_p=0.9,
    ),
    "structured_api": TranslationCapabilities(
        model_family="structured_api",
        supports_system_prompt=True,
        supports_structured_output=True,
        preferred_output_format="json",
        default_max_concurrency=2,
        temperature=0.0,
        top_p=0.9,
    ),
}


def resolve_model_family(requested: str | None, model: str, provider: str) -> str:
    normalized = str(requested or "auto").strip().lower().replace("-", "_")
    aliases = {
        "hymt2": "hy_mt2",
        "hy_mt": "hy_mt2",
        "generic": "generic_chat",
        "chat": "generic_chat",
        "structured": "structured_api",
        "index": "index_translate",
        "indextranslate": "index_translate",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in _CAPABILITY_PRESETS:
        return normalized

    model_lower = str(model or "").lower()
    if re.search(r"index[-_ ]?translate(?:[-_/ .]|$)", model_lower):
        return "index_translate"
    if "hy-mt2" in model_lower or "hymt2" in model_lower:
        return "hy_mt2"
    if provider in {"openai", "gemini"}:
        return "structured_api"
    return "generic_chat"


def get_capabilities(model_family: str) -> TranslationCapabilities:
    return _CAPABILITY_PRESETS.get(model_family, _CAPABILITY_PRESETS["generic_chat"])


def resolve_output_format(requested: str | None, capabilities: TranslationCapabilities) -> str:
    normalized = str(requested or "auto").strip().lower()
    if normalized == "json" and capabilities.supports_structured_output:
        return "json"
    if normalized == "text":
        return "text"
    return capabilities.preferred_output_format


def _matching_glossary(source_text: str, glossary: dict[str, str], limit: int = 20) -> dict[str, str]:
    remaining = source_text.lower()
    matches = []
    # Longest first, masking each match, so コスプレ is not also required
    # where the source only says コスプレイヤー.
    for source, target in sorted(glossary.items(), key=lambda item: len(str(item[0])), reverse=True):
        term = str(source).lower()
        if term and term in remaining:
            matches.append((source, target))
            remaining = remaining.replace(term, "\0")
    return dict(matches[:limit])


def residual_kana_runs(request: TranslationRequest, translation: str) -> tuple[str, ...]:
    remainder = translation
    for element in (*request.preserve_elements, *(request.glossary or {}).values()):
        if element:
            remainder = remainder.replace(element, "")
    return tuple(dict.fromkeys(re.findall(r"[\u3041-\u3096]+", remainder)))


# Last resort for kana the model kept after its repair attempt. Common words
# get a fixed translation; the rest are almost always names or misheard
# terms, which fan subtitles write in romaji rather than leave in kana.
_KANA_WORDS = {
    "いつも": "總是", "なんとか": "某某", "みんな": "大家", "ありがとう": "謝謝",
    "ごめん": "抱歉", "まさか": "難道", "もしかして": "該不會", "けれども": "不過",
    "だから": "所以", "でも": "但是", "なんか": "好像", "たぶん": "大概",
    "もちろん": "當然", "まあ": "嘛", "はい": "好", "です": "", "でした": "",
    "ですね": "", "ですよ": "", "でしょう": "",
    # A lone kana left in Chinese text is a particle, not a name.
    "の": "的", "と": "和", "も": "也", "に": "", "を": "", "は": "", "が": "",
    "で": "", "へ": "", "か": "", "ね": "", "よ": "", "な": "", "わ": "", "さ": "",
}
_KANA_WORDS.update({
    "みなさん": "大家", "みんなさん": "大家", "おじさん": "大叔", "おばさん": "阿姨",
    "おじいさん": "爺爺", "おじいちゃん": "爺爺", "おばあさん": "奶奶", "おばあちゃん": "奶奶",
    "おにいさん": "哥哥", "おにいちゃん": "哥哥", "おねえさん": "姊姊", "おねえちゃん": "姊姊",
    "おかあさん": "媽媽", "おとうさん": "爸爸", "あかちゃん": "寶寶", "お": "", "ご": "",
})
# Standalone meanings only; do not use these to patch longer sentences.
_SHORT_LINE_WORDS = {
    "まだまだ": "還早呢", "どんどん": "不斷", "もっと": "再多一點",
    "もっともっと": "再多一點", "すごい": "好厲害", "すごいすごい": "好厲害",
    "やばい": "不妙", "ほんと": "真的", "ほんとに": "真的", "よし": "好", "じゃあ": "那麼",
    "ねえ": "欸", "うそ": "騙人", "はやく": "快點", "がんばって": "加油",
    "がんばれ": "加油", "おはよう": "早安", "おやすみ": "晚安", "こんばんは": "晚上好",
    "こんにちは": "你好", "ありがとう": "謝謝", "ありがとうございます": "謝謝", "うん": "嗯",
    "ああ": "啊", "おお": "喔", "わあ": "哇", "そうそう": "對對",
    "だめ": "不行", "まって": "等一下", "かわいい": "好可愛", "きれい": "好漂亮",
    "いいね": "不錯耶", "いくよ": "要上囉", "みんな": "大家", "ただいま": "我回來了",
    "おかえり": "歡迎回來", "よろしく": "請多指教", "おつかれ": "辛苦了", "おつかれさま": "辛苦了",
    "ごめん": "抱歉",
    "ごめんね": "抱歉",
    "もちろん": "當然",
    "たぶん": "大概",
    "はい": "好",
    "みなさん": "大家",
    "みんなさん": "大家",
    "たくさん": "很多",
    "おじさん": "大叔",
    "おばさん": "阿姨",
    "あかちゃん": "寶寶",
    "おくさん": "太太",
    "とうさん": "爸爸",
    "おとうさん": "爸爸",
    "かあさん": "媽媽",
    "おかあさん": "媽媽",
    "にいさん": "哥哥",
    "おにいさん": "哥哥",
    "にいちゃん": "哥哥",
    "おにいちゃん": "哥哥",
    "ねえさん": "姊姊",
    "おねえさん": "姊姊",
    "ねえちゃん": "姊姊",
    "おねえちゃん": "姊姊",
    "じいさん": "爺爺",
    "おじいさん": "爺爺",
    "じいちゃん": "爺爺",
    "おじいちゃん": "爺爺",
    "ばあさん": "奶奶",
    "おばあさん": "奶奶",
    "ばあちゃん": "奶奶",
    "おばあちゃん": "奶奶",
    "かあちゃん": "媽媽",
    "とうちゃん": "爸爸",
    "わんちゃん": "狗狗",
    "ねこちゃん": "貓咪",
    "くまさん": "熊熊",
    "うさぎさん": "兔兔",
    "いしゃさん": "醫生",
    "おいしゃさん": "醫生",
    "ぞうさん": "大象",
    "いぬちゃん": "狗狗",
    "ありさん": "螞蟻",
    "おじちゃん": "叔叔",
    "おばちゃん": "阿姨",
}
# Animal stems take any honorific (くまちゃん, ねこさん); other table words
# ending in さん (みなさん, たくさん) are not stem + honorific.
_ANIMAL_STEMS = {"くま": "熊熊", "ねこ": "貓咪", "いぬ": "狗狗", "わん": "狗狗",
                 "うさぎ": "兔兔", "ぞう": "大象"}
_KANA_PHRASES = {
    "皆さん": "大家", "お父さん": "爸爸", "お母さん": "媽媽", "お兄さん": "哥哥",
    "お兄ちゃん": "哥哥", "兄ちゃん": "哥哥", "お姉さん": "姊姊", "お姉ちゃん": "姊姊",
    "姉ちゃん": "姊姊", "赤ちゃん": "寶寶", "奥さん": "太太",
    "お疲れ様": "辛苦了", "お疲れさま": "辛苦了", "お疲れ": "辛苦了",
}
_HONORIFIC_ZH = (("ちゃん", "醬"), ("さん", "桑"), ("くん", "君"))
_ROMAJI = dict(zip(
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉゔ",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho ma mi mu me mo ya yu yo ra ri ru re ro wa o n ga gi gu ge go za ji zu ze zo da ji zu de do ba bi bu be bo pa pi pu pe po a i u e o vu".split()))
_ROMAJI.update({"ゐ": "i", "ゑ": "e", "ゎ": "wa"})
_YOUON = {"ゃ": "ya", "ゅ": "yu", "ょ": "yo"}


def _romanize_hiragana(run: str) -> str:
    out = []
    double = False
    for index, char in enumerate(run):
        if char == "っ":
            double = True
            continue
        if char in _YOUON:
            if out and len(out[-1]) >= 2 and out[-1].endswith("i"):
                stem = out[-1][:-1]
                out[-1] = stem + (_YOUON[char][1:] if stem.endswith(("sh", "ch", "j")) else _YOUON[char])
            else:
                out.append(_YOUON[char])
            continue
        syllable = _ROMAJI.get(char, "")
        if double and syllable:
            syllable = ("t" if syllable.startswith("ch") else syllable[0]) + syllable
        double = False
        out.append(syllable)
    text = "".join(out)
    return text[:1].upper() + text[1:]


_LONG_VOWEL = {"a": "あ", "i": "い", "u": "う", "e": "えい", "o": "うお"}
_SMALL_VOWEL = dict(zip("ぁぃぅぇぉ", "あいうえお"))


def _to_hiragana(text: str) -> str:
    return "".join(chr(ord(char) - 0x60) if 'ァ' <= char <= 'ヶ' else char for char in text)


def _short_line_word(token: str) -> str | None:
    # ー and small vowels stretch the previous vowel: にーちゃん and ねぇちゃん
    # are にいちゃん and ねえちゃん, とーさん is とうさん.
    variants = {""}
    previous = ""
    for char in re.sub(r"ー+", "ー", _to_hiragana(token)):
        if char == "ー" or char in _SMALL_VOWEL:
            vowel = (_ROMAJI.get(previous) or _YOUON.get(previous, ""))[-1:]
            options = {*_LONG_VOWEL.get(vowel, ""), _SMALL_VOWEL.get(char, ""), ""}
            variants = {v + o for v in variants for o in options}
        else:
            variants = {v + char for v in variants}
            previous = char
        if len(variants) > 32:
            return None
    for variant in sorted(variants, key=len, reverse=True):
        for candidate in (variant, variant.removesuffix("っ")):
            if candidate in _SHORT_LINE_WORDS:
                return _SHORT_LINE_WORDS[candidate]
    return None


def short_line_fallback(request: TranslationRequest) -> str | None:
    source = request.source_text.strip()
    if len(source) > 16 or not re.search(r"[\u3041-\u3096]", source):
        return None
    separators = r"[、。，！？!?…～〜・,.「」『』（）()［］\[\]♪♡☆★ｗ\s\u3000]+"
    parts = re.split(f"({separators})", source)
    glossary = request.glossary or {}
    for index in range(0, len(parts), 2):
        token = parts[index]
        if not token:
            continue
        kana = re.fullmatch(r"[\u3041-\u3096\u30a1-\u30faー]+", token)
        if token in glossary:
            localized = glossary[token]
        elif token in request.preserve_elements:
            localized = token
        elif (kana and _short_line_word(token)
              and not (re.search(r"[\u30a1-\u30fa]", token)
                       and re.sub(r"[ーっぁぃぅぇぉ]", "", token).endswith(
                           tuple(h for h, _ in _HONORIFIC_ZH)))):
            # ミナさん is a name, not みなさん.
            localized = _short_line_word(token)
        elif re.fullmatch(r"[\u30a1-\u30faー]+", token):
            # A katakana name; a lone ー or ッ is not one.
            localized = token if re.search(r"[\u30a1-\u30fa]", token.replace("ッ", "")) else None
        else:
            localized = None
            for honorific, chinese in _HONORIFIC_ZH:
                if not token.endswith(honorific):
                    continue
                name = token[:-len(honorific)]
                if name in glossary:
                    localized = glossary[name] + chinese if glossary[name] else None
                    break
                if _to_hiragana(name) in _ANIMAL_STEMS:
                    localized = _ANIMAL_STEMS[_to_hiragana(name)]
                    break
                base = re.sub(r"[ーっぁぃぅぇぉ]", "", _to_hiragana(name))
                # Nicknames are short; longer stems or お〜 are usually words (おきゃくさん).
                # ちーちゃん is a nickname; あーちゃん is a drawn-out vowel.
                stretched = len(base) == 1 and name.endswith("ー") and base not in "あいうえおん"
                if (len(base) < 2 and not stretched) or _short_line_word(name):
                    break
                if re.fullmatch(r"[\u3041-\u3096ー]+", name):
                    if len(base) <= 3 and not name.startswith("お"):
                        localized = _romanize_hiragana(re.sub(r"ー+", "", name)) + chinese
                elif re.fullmatch(r"[\u30a1-\u30faー]+", name):
                    localized = name + chinese
                break
        if not localized:
            return None
        parts[index] = localized
    for index in range(1, len(parts), 2):
        # A bare space between two words reads as a pause.
        parts[index] = "，" if not parts[index].strip() else re.sub(r"\s+", "", parts[index])
    result = "".join(parts).strip("，").translate(
        str.maketrans({"、": "，", ",": "，", "!": "！", "?": "？"}))
    remainder = "".join(_residual_kana_parts(request, result)[::2])
    if (re.search(r"[\u3041-\u3096]", remainder)
            or not any(unicodedata.category(char)[0] in "LN" for char in result)):
        return None
    return result


def _localize_kana_run(run: str) -> str:
    if run in _KANA_WORDS:
        return _KANA_WORDS[run]
    # A one-kana stem is a word of its own (もの, おに), not word + particle.
    stem = run[:-1]
    if (len(stem) > 1 and run[-1] in "はがのにをもとでへやかねよ"
            and (stem in _KANA_WORDS or stem.endswith(tuple(h for h, _ in _HONORIFIC_ZH)))):
        return _localize_kana_run(run[:-1]) + _KANA_WORDS.get(run[-1], "")
    for honorific, chinese in _HONORIFIC_ZH:
        if run == honorific:
            return chinese
        if run.endswith(honorific):
            return _romanize_hiragana(run[:-len(honorific)]) + chinese
    return _romanize_hiragana(run)


def _residual_kana_parts(request: TranslationRequest, translation: str) -> list[str]:
    protected = [element for element in (*request.preserve_elements, *(request.glossary or {}).values())
                 if element]
    if protected:
        pattern = "(" + "|".join(re.escape(e) for e in sorted(set(protected), key=len, reverse=True)) + ")"
        return re.split(pattern, translation)
    return [translation]


def residual_kana_share(request: TranslationRequest, text: str) -> float:
    remainder = "".join(_residual_kana_parts(request, text)[::2])
    return len(re.findall(r"[\u3041-\u3096]", remainder)) / max(1, len(remainder))


def localize_residual_kana(request: TranslationRequest, translation: str) -> str:
    parts = _residual_kana_parts(request, translation)
    phrases = "|".join(re.escape(word) for word in sorted(_KANA_PHRASES, key=len, reverse=True))
    for index in range(0, len(parts), 2):
        part = re.sub(phrases, lambda m: _KANA_PHRASES[m.group(0)], parts[index])
        parts[index] = re.sub(r"[\u3041-\u3096]+", lambda m: _localize_kana_run(m.group(0)), part)
    text = "".join(parts)
    # A dropped particle can leave the quotes that held it.
    return re.sub(r"\u300c\u300d|\u300e\u300f", "", text)


def _kana_repair_line(request: TranslationRequest) -> str:
    if not request.repair or not request.residual_kana:
        return ""
    return ("上次译文残留日文" + "".join(f"「{run}」" for run in request.residual_kana)
            + "，请全部翻成目标语言，不要保留日文假名。")


class TranslationPromptStrategy:
    def __init__(self, prompt: str, capabilities: TranslationCapabilities, output_format: str):
        self.prompt = str(prompt or "").strip()
        self.capabilities = capabilities
        self.output_format = output_format

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        glossary = _matching_glossary(request.source_text, request.glossary or {})
        glossary_line = ""
        if glossary:
            pairs = ", ".join(f"{source}→{target}" for source, target in glossary.items())
            glossary_line = f"Glossary: {pairs}\n"
        context = ""
        if request.previous_original:
            context = (
                "Previous subtitle for context only. Do not repeat it:\n"
                f"{request.previous_original}\n\n"
            )
        user_content = f"{glossary_line}{context}{self.prompt}:\n{request.source_text}".strip()
        system_instruction = (
            "You are a professional translator. Translate accurately and concisely. "
            "Output only the translation without explanations or Markdown."
        )
        if self.output_format == "json":
            system_instruction += ' Return JSON with exactly one key named "translation".'
        return PreparedPrompt(
            system_instruction=system_instruction,
            user_content=user_content,
            output_format=self.output_format,
            temperature=self.capabilities.temperature,
            top_p=self.capabilities.top_p,
            top_k=self.capabilities.top_k,
            repetition_penalty=self.capabilities.repetition_penalty,
        )


class HyMT2PromptStrategy(TranslationPromptStrategy):
    optimizer_settings = None

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        if self.optimizer_settings is not None:
            from .hy_mt2_optimizer import build_prompt
            prompt = build_prompt(request.source_text, self.prompt,
                                  request.glossary or {}, request.previous_sources,
                                  self.optimizer_settings)
            additions = []
            if _kana_repair_line(request):
                additions.append(_kana_repair_line(request))
            if request.preserve_elements:
                additions.append("〖必須原樣保留，數量及順序不變〗\n" + "、".join(request.preserve_elements))
            if request.candidates and not request.repair:
                candidates = _matching_glossary(request.source_text, request.candidates,
                                               self.optimizer_settings.max_terms)
                if candidates:
                    additions.append("〖不確定辨識候選，僅供消歧，不得強制改寫〗\n" + str(candidates))
            if additions:
                prompt = "\n\n".join(additions + [prompt])
            return PreparedPrompt(
                system_instruction=None,
                user_content=prompt,
                output_format="text",
                temperature=self.capabilities.temperature,
                top_p=self.capabilities.top_p,
                top_k=self.capabilities.top_k,
                repetition_penalty=self.capabilities.repetition_penalty,
            )
        blocks = []
        if _kana_repair_line(request):
            blocks.append(_kana_repair_line(request))
        glossary = _matching_glossary(request.source_text, request.glossary or {})
        if glossary:
            terms = "\n".join(f"{source} 翻译成 {target}" for source, target in glossary.items())
            blocks.append(f"参考下面的翻译：\n{terms}")
        if request.previous_original:
            blocks.append(
                "〖背景信息，仅供理解，不要翻译或重复〗\n"
                f"{request.previous_original}"
            )
        blocks.append(f"{self.prompt}：\n{request.source_text}")
        return PreparedPrompt(
            system_instruction=None,
            user_content="\n\n".join(blocks),
            output_format="text",
            temperature=self.capabilities.temperature,
            top_p=self.capabilities.top_p,
            top_k=self.capabilities.top_k,
            repetition_penalty=self.capabilities.repetition_penalty,
        )


class IndexTranslatePromptStrategy(TranslationPromptStrategy):
    """instTrans single-user format; constraints do not imply JSON decoding."""
    optimizer_settings = None

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        settings = self.optimizer_settings
        target = request.target_language or "Traditional Chinese"
        if target.lower().replace("_", "-") in {"traditional chinese", "zh-tw", "zh-hant"}:
            target = "繁體中文（台灣用語）"
        constraints = []
        background = ""
        if settings is not None:
            if not request.repair:
                if re.search(r"[\u3040-\u30ff]", request.source_text):
                    constraints.append("【注意】 普通日语词语、助词及语气词都要翻成目标语言，不要留下日文；只按指定术语表或保留要求保留原文专名。")
            terms = _matching_glossary(request.source_text, request.glossary or {}, settings.max_terms)
            if terms:
                constraints.append("【硬性要求】 专名/术语对照: " + "、".join(f"{s}→{t}" for s, t in terms.items()))
            for element in request.preserve_elements:
                if element and element in request.source_text:
                    constraints.append(f"【硬性要求】 原样保留 {element} 的数量及出现顺序。")
            if not request.repair:
                if settings.style and settings.style_text.strip():
                    constraints.append("【注意】 " + settings.style_text.strip()[:500])
                if settings.preferences.strip():
                    constraints.append("【注意】 " + settings.preferences.strip()[:500])
                candidates = _matching_glossary(request.source_text, request.candidates or {}, settings.max_terms)
                if candidates:
                    constraints.append("【注意】 以下是不确定的辨识候选，仅供消歧，不得强制改写原文：" + str(candidates))
                remaining = settings.max_context_chars
                context = []
                for source in reversed(request.previous_sources[-settings.context_window:] if settings.context_window else ()):
                    if source.strip() and len(source) <= remaining:
                        context.insert(0, source)
                        remaining -= len(source)
                if context:
                    background = ("【背景参考】\n以下是之前的原文，仅用于理解。不要翻译、复述或输出本区块。\n"
                                  + "\n".join(context) + "\n【背景参考结束】\n\n")
                    constraints.append("【注意】 只翻译【源文】到【源文结束】之间的本次原文，包括语气词；即使句子尚未说完，也翻译现有内容，不要等待后文或输出空白。")
        # The hint must never follow the source text, or it gets translated too.
        kana_line = _kana_repair_line(request)
        if kana_line and constraints:
            constraints.append("【硬性要求】 " + kana_line)
        if constraints:
            content = (f"请将以下文本翻译成{target}，并且严格遵循所有约束要求。\n\n【源文】\n"
                       + request.source_text.strip() + "\n【源文结束】\n\n【约束要求】\n"
                       + "\n".join(f"{i}. {value}" for i, value in enumerate(constraints, 1))
                       + "\n\n只输出译文，不要有任何额外说明。")
        else:
            content = (f"请将以下文本翻译为{target}，直接输出翻译结果，不要进行任何解释。"
                       + (kana_line if kana_line else "") + f"\n\n{request.source_text.strip()}")
        if background:
            content = background + content
        # Greedy decoding repeats the rejected answer verbatim, so a repair
        # attempt samples to get a different candidate.
        return PreparedPrompt(None, content, "text", 0.5 if request.repair else 0.0, 1.0, None, None)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str = "error"


def validate_translation(request: TranslationRequest, translation: str,
                         history: tuple[tuple[str, str], ...] = (),
                         normalize_output=None, raw_translation=None) -> tuple[ValidationIssue, ...]:
    from .hy_mt2_output_validation import repeats_previous_translation
    issues = []
    if not str(translation or "").strip():
        return (ValidationIssue("empty_output"),)
    leak_text = translation if raw_translation is None else str(raw_translation or "")
    if any(marker in leak_text and marker not in request.source_text
           for marker in ("【源文】", "【约束要求】", "【硬性要求】", "〖背景資訊", "<think>")):
        issues.append(ValidationIssue("prompt_leakage"))
    if normalize_output is None:
        from .qwen3_asr_postprocess import is_traditional_chinese_target, normalize_chinese_script
        normalize_output = lambda text: (normalize_chinese_script(text, "zh-tw")
            if is_traditional_chinese_target(request.target_language) else text)
    translation = normalize_output(translation)
    if not str(translation or "").strip():
        return tuple(issues) + (ValidationIssue("empty_output"),)
    from dataclasses import replace
    request = replace(request, glossary={source: normalize_output(target) if target else target
                      for source, target in (request.glossary or {}).items()})
    target_language = str(request.target_language or "").strip().lower().replace("_", "-")
    if target_language in {"traditional chinese", "simplified chinese", "chinese", "zh", "zh-tw", "zh-hant", "zh-cn", "zh-hans", "繁體中文", "繁体中文", "简体中文"}:
        # Only reject exact Japanese copies. Names and explicitly preserved spans
        # can legitimately retain kana; Chinese-only phrases can match the source.
        source = request.source_text.strip()
        remainder = source
        for element in request.preserve_elements:
            if element:
                remainder = remainder.replace(element, "")
        for term, fixed in (request.glossary or {}).items():
            if term == fixed and term:
                remainder = remainder.replace(term, "")
        if translation.strip() == source and re.search(r"[\u3041-\u3096]", remainder):
            issues.append(ValidationIssue("untranslated_source"))
        output_remainder = translation
        for element in request.preserve_elements:
            if element:
                output_remainder = output_remainder.replace(element, "")
        for fixed in (request.glossary or {}).values():
            if fixed:
                output_remainder = output_remainder.replace(fixed, "")
        kana_count = len(re.findall(r"[\u3041-\u3096]", output_remainder))
        if kana_count >= 3 and kana_count / max(1, len(output_remainder.strip())) >= 0.25:
            issues.append(ValidationIssue("target_language_mismatch"))
        # Sparse common words can hide inside an otherwise Chinese sentence.
        # Compare whole kana runs so a name containing a substring is exempt.
        common_words = {'まさか', 'もしかして', 'けれども', 'だから', 'でも',
                        'なんか', 'です', 'でした', 'ですね', 'ですよ', 'でしょう',
                        'ごめん', 'ありがとう', 'たぶん', 'もちろん', 'まあ'}
        if (common_words.intersection(re.findall(r"[\u3041-\u3096]+", output_remainder))
                and not any(issue.code == 'target_language_mismatch' for issue in issues)):
            issues.append(ValidationIssue('target_language_mismatch'))
        # Catch newly generated broken romanizations such as Moemoebaウ without
        # banning katakana names or names explicitly preserved by the glossary.
        hybrids = re.findall(r'(?<![A-Za-z])[A-Za-z]{4,}[\u30a1-\u30fa]{1,2}(?![\u30a1-\u30fa])', output_remainder)
        if any(token not in request.source_text for token in hybrids):
            if not any(issue.code == 'target_language_mismatch' for issue in issues):
                issues.append(ValidationIssue('target_language_mismatch'))
        if (re.search(r"[\u3041-\u3096]+", output_remainder)
                and not any(issue.code == "target_language_mismatch" for issue in issues)):
            issues.append(ValidationIssue("residual_kana"))
    if '\n' in translation and '\n' not in request.source_text:
        if request.previous_sources and len([line for line in translation.splitlines() if line.strip()]) > 1:
            # A single live segment has no requested line layout. Multiple lines
            # in a contextual reply can be a translation of the background.
            issues.append(ValidationIssue('unexpected_multiline_output'))
        from .hy_mt2_output_validation import _comparable
        lines = [_comparable(line) for line in translation.splitlines()]
        for previous_source, previous_output in history[-3:]:
            old = _comparable(previous_output)
            if len(old) >= 4 and old in lines and _comparable(previous_source) != _comparable(request.source_text):
                if not any(issue.code == 'context_echo_rejected' for issue in issues):
                    issues.append(ValidationIssue('context_echo_rejected'))
                break
    if repeats_previous_translation(request.source_text, translation, history):
        issues.append(ValidationIssue("context_echo_rejected"))
    if any(target not in translation for target in _matching_glossary(request.source_text, request.glossary or {}, len(request.glossary or {})).values() if target):
        issues.append(ValidationIssue("fixed_term_missing"))
    elements = [element for element in request.preserve_elements if element and element in request.source_text]
    if any(translation.count(e) != request.source_text.count(e) for e in elements):
        issues.append(ValidationIssue("preserve_element_changed"))
    elif elements:
        pattern = "|".join(re.escape(e) for e in sorted(set(elements), key=len, reverse=True))
        if re.findall(pattern, translation) != re.findall(pattern, request.source_text):
            issues.append(ValidationIssue("preserve_element_order"))
    return tuple(issues)


def create_prompt_strategy(
    model_family: str,
    prompt: str,
    output_format: str,
) -> TranslationPromptStrategy:
    capabilities = get_capabilities(model_family)
    if model_family == "hy_mt2":
        return HyMT2PromptStrategy(prompt, capabilities, "text")
    if model_family == "index_translate":
        return IndexTranslatePromptStrategy(prompt, capabilities, "text")
    return TranslationPromptStrategy(prompt, capabilities, output_format)


def parse_translation_output(completion: Any, output_format: str) -> str:
    text = str(completion or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    if output_format != "json":
        return text

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return text
    try:
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return text
    translation = payload.get("translation")
    return str(translation).strip() if translation else text
