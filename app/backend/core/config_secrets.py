from copy import deepcopy


MASK_PREFIX = "••••"
# 明確列出敏感欄位，避免誤遮罩 max_output_tokens 等一般設定。
SECRET_KEYS = frozenset({
    "openai_api_key", "google_api_key", "api_key", "cqhttp_token",
    "telegram_bot_token", "cookies", "cookies_by_site", "discord_webhook_url",
    "hy_mt2_lm_studio_api_key", "hy_mt2_llama_cpp_api_key",
    "index_translate_lm_studio_api_key", "index_translate_llama_cpp_api_key",
    "lan_admin_password",
})


def _mask(value):
    if isinstance(value, str) and value:
        return MASK_PREFIX + value[-4:] if len(value) >= 8 else MASK_PREFIX * 2
    return deepcopy(value)


def _output(value, omit=False):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in SECRET_KEYS:
                if not omit:
                    result[key] = ({site: _mask(cookie) for site, cookie in item.items()}
                                   if key == "cookies_by_site" and isinstance(item, dict)
                                   else _mask(item))
            else:
                result[key] = _output(item, omit)
        return result
    if isinstance(value, list):
        return [_output(item, omit) for item in value]
    return deepcopy(value)


def mask_secrets(config):
    """回傳遮罩後的深層副本，不影響執行時使用的真實憑證。"""
    return _output(config)


def omit_secrets(config):
    """匯出預設移除敏感欄位。"""
    return _output(config, omit=True)


def _restore(value, current):
    if isinstance(value, str) and value.startswith(MASK_PREFIX):
        return deepcopy(current) if current is not None else ""
    return deepcopy(value)


def restore_masked_secrets(incoming, current):
    """還原 UI 遮罩；列表以穩定識別欄位配對，缺少的密鑰保持原值。"""
    if isinstance(incoming, dict):
        current = current if isinstance(current, dict) else {}
        result = {}
        for key, value in incoming.items():
            stored = current.get(key)
            if key == "cookies_by_site" and isinstance(value, dict):
                stored = stored if isinstance(stored, dict) else {}
                result[key] = {site: _restore(cookie, stored.get(site))
                               for site, cookie in value.items()}
            elif key in SECRET_KEYS:
                result[key] = _restore(value, stored)
            else:
                result[key] = restore_masked_secrets(value, stored)
        for key in SECRET_KEYS:
            if key not in result and key in current:
                result[key] = deepcopy(current[key])
        return result
    if isinstance(incoming, list):
        stored_items = current if isinstance(current, list) else []
        result = []
        for item in incoming:
            stored = None
            if isinstance(item, dict):
                identity = next((key for key in ("id", "name") if item.get(key)), None)
                if identity:
                    stored = next((entry for entry in stored_items
                                   if isinstance(entry, dict)
                                   and entry.get(identity) == item[identity]), None)
            result.append(restore_masked_secrets(item, stored))
        return result
    return deepcopy(incoming)
