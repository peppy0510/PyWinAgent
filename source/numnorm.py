# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

description:
Korean text normalization for the TTS pipeline (pure stdlib, no deps).
Supertonic reads raw digits inconsistently (Sino vs native, digit-by-digit,
sometimes the wrong language) and, since a request carries ONE language token,
short English acronyms embedded in Korean come out awkward. ttsspeak passes
text through here first to turn numerals into spoken Korean and known short
acronyms into their Korean spelling; whatever English is left (real words like
GitHub / commit) is handled downstream by ttsspeak's per-language chunking.

Rules:
  - integers -> Sino-Korean cardinal      123 -> 백이십삼,  18000 -> 만 팔천
  - counters -> native reading when 1..99  3개 -> 세 개,  25명 -> 스물다섯 명
                (>=100 stays Sino: 100개 -> 백 개)
  - decimals  3.14 -> 삼 점 일 사   (fraction digits read one by one)
  - versions  1.3.1 -> 일 점 삼 점 일   (each dotted segment a cardinal)
  - thousands separators stripped   3,000원 -> 삼천 원
  - percent   50% -> 오십 퍼센트
  - leading-zero ids read digit-by-digit   010 -> 공일공
  - known acronyms -> Korean spelling   PR -> 피알,  API -> 에이피아이,  JSON -> 제이슨
                (whitelist only, so all-caps WORDS like ERROR/TODO stay English)

Usage:
  python numnorm.py <infile-utf8> <outfile-utf8>     # normalize a file
  python numnorm.py --selftest <resultfile-utf8>     # run the built-in tests
Never raises to the caller for real text; on any surprise it returns input
unchanged (ttsspeak also falls back to the original text if this errors).
'''


import re
import sys


SINO_DIGITS = ['영', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
SMALL_UNITS = ['', '십', '백', '천']
BIG_UNITS = ['', '만', '억', '조', '경']

NATIVE_ONES = ['', '한', '두', '세', '네', '다섯', '여섯', '일곱', '여덟', '아홉']
NATIVE_TENS = ['', '열', '스무', '서른', '마흔', '쉰', '예순', '일흔', '여든', '아흔']

# native counters: a 1..99 count right before one of these is read the native way.
NATIVE_UNITS = [
    '시간', '개', '시', '명', '마리', '대', '살', '잔', '병', '그릇', '그루', '송이',
    '켤레', '벌', '채', '척', '판', '줄', '곳', '군데', '가지', '봉지', '조각', '갑',
    '달', '포기', '자루', '손', '뭉치', '근', '말', '되', '쌈', '컵', '스푼',
]
# Sino counters that share a native counter's prefix must win the longest-match
# (개월/개국 vs the native 개), plus common Sino units we want spaced for prosody.
SINO_UNITS = [
    '개월', '개국', '개년', '인분',
    '년', '월', '일', '분', '초', '원', '층', '번', '호', '회', '차', '등', '위',
    '도', '인', '쪽', '절', '교시', '학년', '퍼센트', '킬로미터', '센티미터',
    '밀리미터', '제곱미터', '미터', '킬로그램', '킬로', '그램', '평', '달러',
    '엔', '위안', '기가', '메가', '바이트', '초당', '주', '교', '권', '화',
    '건', '부', '매', '종', '편', '곡',
]

_UNITS = [(u, 'sino') for u in SINO_UNITS] + [(u, 'native') for u in NATIVE_UNITS]
_UNITS.sort(key=lambda uk: -len(uk[0]))          # longest first (개월 before 개)
_UNIT_KIND = {u: k for u, k in _UNITS}
_UNIT_ALT = '|'.join(re.escape(u) for u, _ in _UNITS)

_THOUSANDS = re.compile(r'\d{1,3}(?:,\d{3})+')
_PERCENT = re.compile(r'(?<=\d)\s*%')
_TOKEN = re.compile(
    r'(?P<ver>\d+(?:\.\d+){2,})'
    r'|(?P<dec>\d+\.\d+)'
    r'|(?P<num>\d+)\s*(?P<unit>' + _UNIT_ALT + r')?'
)

# English letter names in Korean, for spelling out acronyms (PR -> 피 + 알).
ALPHA_KO = {
    'A': '에이', 'B': '비', 'C': '씨', 'D': '디', 'E': '이', 'F': '에프', 'G': '지',
    'H': '에이치', 'I': '아이', 'J': '제이', 'K': '케이', 'L': '엘', 'M': '엠', 'N': '엔',
    'O': '오', 'P': '피', 'Q': '큐', 'R': '알', 'S': '에스', 'T': '티', 'U': '유',
    'V': '브이', 'W': '더블유', 'X': '엑스', 'Y': '와이', 'Z': '지',
}
# Whitelist of short acronyms to read as Korean 음차 (spelled letter-by-letter unless
# a value overrides with a word reading). WHITELIST on purpose: all-caps English WORDS
# (ERROR, TODO, POST, NULL, README...) are NOT here, so they stay English and get their
# native pronunciation via ttsspeak's per-language chunking instead of being mis-spelled.
_ACRONYM_WORD = {'RAM': '램', 'ROM': '롬', 'JSON': '제이슨', 'YAML': '야믈', 'REST': '레스트', 'OK': '오케이'}
_ACRONYM_SPELL = [
    'PR', 'API', 'CI', 'CD', 'DB', 'UI', 'UX', 'URL', 'URI', 'ID', 'SDK', 'CLI', 'MCP',
    'TTS', 'STT', 'AI', 'ML', 'OS', 'PC', 'DNS', 'SSH', 'SQL', 'AWS', 'GCP', 'GPU', 'CPU',
    'IDE', 'CSS', 'HTML', 'XML', 'JWT', 'RPC', 'VM', 'QA', 'HTTP', 'HTTPS', 'TV', 'IT',
    'HR', 'FTP', 'IP', 'OTP', 'PDF', 'CSV', 'PNG', 'JPG', 'GIF', 'USB', 'SNS', 'QR', 'PW',
]
ACRONYMS = dict(_ACRONYM_WORD)
for _a in _ACRONYM_SPELL:
    ACRONYMS.setdefault(_a, ''.join(ALPHA_KO[c] for c in _a))
# a maximal run of ASCII letters that is exactly an all-caps token (not part of a longer
# mixed-case word like GraphQL, and not a plural like APIs) -> transliterate if whitelisted.
_ACRONYM_RE = re.compile(r'(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])')


def _acronym_repl(m):
    tok = m.group(0)
    return ACRONYMS.get(tok, tok)          # unknown all-caps -> leave for native-English readout


# Fixed pronunciations for specific project terms the model would otherwise misread. Keys
# LOWERCASE; matched case-insensitively and whole-word (so 'tkmix' matches, 'tkmixer' does not).
# Runs first in normalize() so the Korean reading is left untouched by the later passes.
WORDS = {
    'tkmix': '티케이믹스',                  # T-K + mix
}
_WORD_RE = re.compile(
    r'(?<![A-Za-z0-9])(?:' + '|'.join(re.escape(w) for w in WORDS) + r')(?![A-Za-z0-9])',
    re.IGNORECASE)


def _word_repl(m):
    return WORDS[m.group(0).lower()]


def sino_group(n):
    '''0..9999 -> Korean, dropping 일 before 십/백/천 (15 -> 십오, not 일십오).'''
    out = ''
    for pos in (3, 2, 1, 0):
        d = (n // (10 ** pos)) % 10
        if d == 0:
            continue
        if pos == 0:
            out += SINO_DIGITS[d]
        elif d == 1:
            out += SMALL_UNITS[pos]
        else:
            out += SINO_DIGITS[d] + SMALL_UNITS[pos]
    return out


def sino_cardinal(n):
    '''Non-negative int -> full Sino-Korean cardinal (만 팔천, 백이십삼만 ...).'''
    if n == 0:
        return '영'
    groups = []
    while n > 0:
        groups.append(n % 10000)
        n //= 10000
    parts = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        gstr = sino_group(g)
        if idx == 1 and g == 1:      # 만 drops its leading 일 (만, not 일만); 억/조 keep it
            gstr = ''
        parts.append(gstr + BIG_UNITS[idx])
    return ' '.join(p for p in parts if p)


def native_prenoun(n):
    '''1..99 -> native counting form (pre-noun): 3 -> 세, 20 -> 스무, 21 -> 스물한.'''
    if not (1 <= n <= 99):
        return None
    t, o = divmod(n, 10)
    if t == 0:
        return NATIVE_ONES[o]
    tens = NATIVE_TENS[t]
    if o == 0:
        return tens
    if t == 2:                       # 스무 is standalone-only; 2X compounds use 스물
        tens = '스물'
    return tens + NATIVE_ONES[o]


def _digit_by_digit(s):
    return ''.join('공' if d == '0' else SINO_DIGITS[int(d)] for d in s)


def _replace(m):
    if m.group('ver'):
        return ' 점 '.join(sino_cardinal(int(s)) for s in m.group('ver').split('.'))
    if m.group('dec'):
        intp, frac = m.group('dec').split('.')
        return sino_cardinal(int(intp)) + ' 점 ' + ' '.join(SINO_DIGITS[int(d)] for d in frac)
    num = m.group('num')
    unit = m.group('unit')
    if len(num) > 1 and num[0] == '0':       # 010, 007 -> id, read each digit
        return _digit_by_digit(num) + ((' ' + unit) if unit else '')
    n = int(num)
    if unit:
        if _UNIT_KIND.get(unit) == 'native':
            nat = native_prenoun(n)
            if nat is not None:
                return nat + ' ' + unit
        return sino_cardinal(n) + ' ' + unit
    return sino_cardinal(n)


def normalize(text):
    try:
        text = _WORD_RE.sub(_word_repl, text)
        text = _ACRONYM_RE.sub(_acronym_repl, text)
        text = _THOUSANDS.sub(lambda m: m.group(0).replace(',', ''), text)
        text = _PERCENT.sub('퍼센트', text)
        text = _TOKEN.sub(_replace, text)
    except Exception:
        pass
    return text


TESTS = [
    # symptom 1: Sino vs native counter
    ('3개', '세 개'),
    ('3시', '세 시'),
    ('1개', '한 개'),
    ('2대', '두 대'),
    ('4명', '네 명'),
    ('25명', '스물다섯 명'),
    ('20개', '스무 개'),
    ('21개', '스물한 개'),
    ('11마리', '열한 마리'),
    ('100개', '백 개'),               # >=100 stays Sino
    ('3시간', '세 시간'),
    ('3개월', '삼 개월'),             # Sino counter wins longest-match over native 개
    ('30분', '삼십 분'),             # minute is Sino
    ('3시 30분', '세 시 삼십 분'),
    # symptom 2: versions / decimals / symbols
    ('1.3.1', '일 점 삼 점 일'),
    ('1.10.2', '일 점 십 점 이'),
    ('3.14', '삼 점 일 사'),
    ('0.5', '영 점 오'),
    ('50%', '오십 퍼센트'),
    ('3,000원', '삼천 원'),
    ('1,234,567', '백이십삼만 사천오백육십칠'),
    ('18000', '만 팔천'),
    ('포트 18000', '포트 만 팔천'),
    ('2025년', '이천이십오 년'),
    ('3월 15일', '삼 월 십오 일'),
    # acronyms (음차, whitelist only)
    ('PR', '피알'),
    ('API', '에이피아이'),
    ('DB', '디비'),
    ('CI/CD', '씨아이/씨디'),
    ('JSON', '제이슨'),
    ('PR을 3개 머지', '피알을 세 개 머지'),
    ('API 응답', '에이피아이 응답'),
    ('2건', '이 건'),
    ('5부', '오 부'),
    ('ERROR', 'ERROR'),               # all-caps WORD not in whitelist -> stays English
    ('TODO 정리', 'TODO 정리'),
    ('GitHub Actions', 'GitHub Actions'),   # mixed case -> untouched (native English later)
    ('APIs', 'APIs'),                 # plural (trailing lowercase) -> not an acronym match
    # fixed project-term pronunciations (WORDS map, case-insensitive whole-word)
    ('tkmix', '티케이믹스'),
    ('TKMIX', '티케이믹스'),
    ('tkmix에 커밋', '티케이믹스에 커밋'),
    ('tkmixer', 'tkmixer'),           # word-boundary: not a whole-word match
    # cardinals / edges
    ('123', '백이십삼'),
    ('10', '십'),
    ('10001', '만 일'),
    ('0', '영'),
    ('010', '공일공'),
    ('버전 2.0', '버전 이 점 영'),
    ('숫자가 없는 문장', '숫자가 없는 문장'),
]


def _selftest(result_path):
    lines = []
    ok = 0
    for src, want in TESTS:
        got = normalize(src)
        mark = 'PASS' if got == want else 'FAIL'
        if got == want:
            ok += 1
        lines.append(f'{mark}  {src!r:<14} want={want:20} got={got}')
    lines.insert(0, f'{ok}/{len(TESTS)} passed')
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--selftest':
        _selftest(sys.argv[2])
        return
    if len(sys.argv) >= 3:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            text = f.read()
        with open(sys.argv[2], 'w', encoding='utf-8') as f:
            f.write(normalize(text))


if __name__ == '__main__':
    main()
