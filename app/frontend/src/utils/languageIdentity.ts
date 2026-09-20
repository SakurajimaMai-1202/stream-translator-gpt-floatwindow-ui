export function sameLanguage(source: string, target: string): boolean {
  const aliases: Record<string, string> = {
    japanese: 'ja', '日文': 'ja', 'ja-jp': 'ja',
    english: 'en', '英文': 'en', 'en-us': 'en', 'en-gb': 'en',
    korean: 'ko', '韓文': 'ko', 'ko-kr': 'ko',
    'traditional chinese': 'zh-hant', '繁體中文': 'zh-hant', 'zh-tw': 'zh-hant',
    'simplified chinese': 'zh-hans', '簡體中文': 'zh-hans', 'zh-cn': 'zh-hans',
  };
  const normalize = (value: string) => {
    const key = (value || '').trim().toLowerCase().replace(/_/g, '-');
    return aliases[key] || key;
  };
  const input = normalize(source);
  return !!input && input !== 'auto' && input === normalize(target);
}
