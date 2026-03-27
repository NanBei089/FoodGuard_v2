from __future__ import annotations

import re

REGEX_FLAGS = re.IGNORECASE

INGREDIENT_TEXT_LIMIT = 500
SPACE_RE = re.compile(r"\s+")
TOPIC_TRIM_EDGE_RE = re.compile(
    r"^[\s:：;；，,、。.!！？?\-]+|[\s:：;；，,、。.!！？?\-]+$"
)
INGREDIENT_NOISE_EDGE_RE = re.compile(
    r"^[\s:：;；，,、。.!！？?\-*]+|[\s:：;；，,、。.!！？?\-*]+$"
)
NOISE_LINE_RE = re.compile(
    r'^(?:详情请见扫码后活动规则|[0-9\s"]{6,}|本产品由盒马及盒马认可的经销商专卖)$'
)

INGREDIENT_START_LABEL_PATTERNS: tuple[str, ...] = (
    r"配\s*料\s*表?",
    r"原\s*料(?:\s*表)?",
    r"成\s*分(?:\s*表)?",
)

INGREDIENT_SECTION_END_PATTERNS: tuple[str, ...] = (
    r"致\s*敏\s*(?:原(?:信\s*息)?|物\s*质(?:信\s*息)?)",
    r"过\s*敏\s*原(?:信\s*息)?",
    r"本\s*产\s*品\s*含",
    r"此\s*产\s*品\s*含",
    r"营\s*养\s*成\s*分(?:表)?",
    r"NRV",
    r"贮\s*存\s*条\s*件",
    r"保\s*存\s*方\s*法",
    r"保\s*质\s*期",
    r"质\s*保\s*期",
    r"生\s*产\s*日\s*期",
    r"生\s*产\s*日",
    r"到\s*期",
    r"失\s*效",
    r"有\s*效\s*期(?:至)?",
    r"食\s*品\s*生\s*产\s*许\s*可\s*证",
    r"生\s*产\s*许\s*可\s*证",
    r"执\s*行\s*标\s*准",
    r"产\s*品\s*标\s*准(?:\s*号|\s*代\s*号)?",
    r"产\s*品\s*(?:类\s*别|类\s*型)",
    r"生\s*产\s*商",
    r"制\s*造\s*商",
    r"生\s*产\s*者",
    r"委\s*托\s*方",
    r"受\s*委\s*托\s*方",
    r"厂\s*址",
    r"地\s*址",
    r"产\s*地",
    r"原\s*产\s*国",
    r"电\s*话",
    r"联\s*系\s*方\s*式",
    r"服\s*务\s*热\s*线",
    r"邮\s*编",
    r"净\s*含\s*量",
    r"净\s*重",
    r"规\s*格",
    r"食\s*用\s*方\s*法",
    r"SC\s*\d+",
)

INGREDIENT_NOTE_PATTERNS: tuple[str, ...] = (
    r"注\s*[:：]",
    r"备\s*注\s*[:：]",
    r"说\s*明\s*[:：]",
    r"提\s*示\s*[:：]",
    r"温\s*馨\s*提\s*示\s*[:：]?",
)

INGREDIENT_MARKETING_END_PATTERNS: tuple[str, ...] = (
    r"官\s*方\s*(?:微\s*博|微\s*信(?:公\s*众\s*号)?)",
    r"微\s*信\s*公\s*众\s*号",
    r"果\s*汁\s*含\s*量",
    r"0\s*添\s*加",
    r"(?:总\s*添加量|平\s*均\s*添加量)\s*(?:为|不\s*少\s*于|[:：≥≤])",
    r"[A-Za-z0-9\u4e00-\u9fff+]{2,}\s*含\s*量\s*(?:≥|≤)",
)

INGREDIENT_VALID_TERM_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
INGREDIENT_WRAPPED_TOKEN_RE = re.compile(
    r"^(?P<outer>[^()（）]+?)[（(](?P<inner>.+)[）)]$"
)
INGREDIENT_CATEGORY_WRAPPER_RE = re.compile(r"^(食品添加剂|复配食品添加剂)$")
INGREDIENT_MEASURE_SUFFIX_RE = re.compile(
    r"(?:≥|≤|约|不少于)?\s*\d+(?:\.\d+)?\s*(?:%|％|g|kg|克|千克|ml|mL|ML|毫升|升)$",
    REGEX_FLAGS,
)
INGREDIENT_PAREN_MEASURE_SUFFIX_RE = re.compile(
    r"[（(]\s*(?:≥|≤|约|不少于)?\s*\d+(?:\.\d+)?\s*(?:%|％|g|kg|克|千克|ml|mL|ML|毫升|升)\s*[）)]$",
    REGEX_FLAGS,
)
INGREDIENT_INNER_SPLIT_TRIGGER_RE = re.compile(r"[、,，;；/|]")
INGREDIENT_NOISE_CHAR_RE = re.compile(r"\$")
INGREDIENT_SINGLE_CHAR_KEEP_SET = {"盐", "糖", "油", "水", "醋", "茶"}
INGREDIENT_TOP_LEVEL_DELIMITERS = {"、", ",", "，", ";", "；", "/", "|"}
INGREDIENT_MERGE_PREFIX_TOKENS = {"单", "双"}
INGREDIENT_LATEX_REPLACEMENTS = (
    ("\\geq", "≥"),
    ("\\leq", "≤"),
    ("\\%", "%"),
)

OTHER_TOPIC_ORDER = (
    "storage",
    "shelf_life",
    "mfg_date",
    "exp_date",
    "license",
    "standard",
    "manufacturer",
    "net_content",
)

OTHER_TOPIC_REGEX: dict[str, tuple[str, ...]] = {
    "storage": (
        r"贮\s*存\s*条\s*件",
        r"保\s*存\s*方\s*法",
        r"储\s*存\s*条\s*件",
        r"存\s*放",
        r"储\s*藏\s*(?:方\s*法|条\s*件)",
        r"贮\s*藏\s*(?:方\s*法|条\s*件)",
        r"冷\s*藏",
        r"冷\s*冻",
        r"常\s*温\s*保\s*存",
        r"阴\s*凉\s*干\s*燥",
        r"避\s*免\s*阳\s*光\s*直\s*射",
        r"置\s*于\s*阴\s*凉",
    ),
    "shelf_life": (
        r"保\s*质\s*期",
        r"质\s*保\s*期",
        r"有\s*效\s*期",
        r"最\s*佳\s*食\s*用\s*期",
        r"保\s*存\s*期",
        r"保\s*存\s*期\s*限",
        r"食\s*用\s*期\s*限",
        r"建\s*议\s*食\s*用\s*期\s*限",
    ),
    "mfg_date": (
        r"生\s*产\s*日\s*期",
        r"生\s*产\s*日",
        r"制\s*造\s*日\s*期",
        r"生\s*产\s*时\s*间",
        r"生\s*产\s*批\s*号",
        r"生\s*产\s*批\s*次",
    ),
    "exp_date": (
        r"到\s*期",
        r"失\s*效",
        r"有\s*效\s*期\s*至",
        r"截\s*止",
        r"截\s*止\s*日\s*期",
        r"到\s*期\s*日\s*期",
        r"失\s*效\s*日\s*期",
        r"使\s*用\s*期\s*限",
    ),
    "license": (
        r"食\s*品\s*生\s*产\s*许\s*可\s*证(?:编\s*号)?",
        r"生\s*产\s*许\s*可\s*证(?:编\s*号)?",
        r"许\s*可\s*证\s*编\s*号",
        r"SC\s*\d+",
    ),
    "standard": (
        r"执\s*行\s*标\s*准",
        r"执\s*行\s*标\s*准\s*号",
        r"产\s*品\s*标\s*准\s*代\s*号",
        r"产\s*品\s*标\s*准\s*号",
        r"标\s*准\s*号",
        r"(?:GB|GB/T|QB|SB|NY|T/)\s*[\d\.\-]+",
    ),
    "manufacturer": (
        r"产\s*地",
        r"原\s*产\s*地",
        r"生\s*产\s*商",
        r"生\s*产\s*厂\s*家",
        r"生\s*产\s*企\s*业",
        r"制\s*造\s*商",
        r"制\s*造\s*企\s*业",
        r"委\s*托\s*方",
        r"受\s*委\s*托\s*方",
        r"出\s*品\s*商",
        r"监\s*制",
        r"经\s*销\s*商",
        r"代\s*理\s*商",
        r"厂\s*址",
        r"生\s*产\s*地\s*址",
        r"地\s*址",
        r"电\s*话",
        r"联\s*系\s*电\s*话",
        r"联\s*系\s*方\s*式",
        r"服\s*务\s*热\s*线",
        r"客\s*服\s*热\s*线",
        r"邮\s*编",
        r"邮\s*政\s*编\s*码",
    ),
    "net_content": (
        r"净\s*含\s*量",
        r"净\s*重",
        r"规\s*格",
        r"含\s*量",
        r"重\s*量",
        r"容\s*量",
        r"净\s*含\s*量\s*/\s*规\s*格",
    ),
}

MANUFACTURER_GROUP_TOPICS = {"manufacturer"}


def _compile_union(*parts: str, suffix: str = "") -> re.Pattern[str]:
    return re.compile(f"(?P<anchor>{'|'.join(parts)}){suffix}", REGEX_FLAGS)


INGREDIENT_LABEL_RE = _compile_union(
    *INGREDIENT_START_LABEL_PATTERNS, suffix=r"\s*[:：]?"
)
INLINE_INGREDIENT_LABEL_RE = _compile_union(
    *INGREDIENT_START_LABEL_PATTERNS, suffix=r"\s*[:：]"
)
INGREDIENT_END_RE = _compile_union(
    *INGREDIENT_SECTION_END_PATTERNS,
    *INGREDIENT_NOTE_PATTERNS,
    *INGREDIENT_MARKETING_END_PATTERNS,
)
INGREDIENT_BOUNDARY_RE = _compile_union(
    *INGREDIENT_SECTION_END_PATTERNS,
    *INGREDIENT_NOTE_PATTERNS,
    *INGREDIENT_MARKETING_END_PATTERNS,
)
NUTRITION_HEADER_RE = re.compile(r"营\s*养\s*成\s*分|NRV", REGEX_FLAGS)

OTHER_TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    topic_name: re.compile("(" + "|".join(patterns) + ")", REGEX_FLAGS)
    for topic_name, patterns in OTHER_TOPIC_REGEX.items()
}
MANUFACTURER_LINE_RE = re.compile(
    "^(" + "|".join(OTHER_TOPIC_REGEX["manufacturer"]) + ")",
    REGEX_FLAGS,
)


__all__ = [
    "INGREDIENT_BOUNDARY_RE",
    "INGREDIENT_CATEGORY_WRAPPER_RE",
    "INGREDIENT_END_RE",
    "INGREDIENT_INNER_SPLIT_TRIGGER_RE",
    "INGREDIENT_LABEL_RE",
    "INGREDIENT_LATEX_REPLACEMENTS",
    "INGREDIENT_MEASURE_SUFFIX_RE",
    "INGREDIENT_MERGE_PREFIX_TOKENS",
    "INGREDIENT_NOISE_CHAR_RE",
    "INGREDIENT_NOISE_EDGE_RE",
    "INGREDIENT_PAREN_MEASURE_SUFFIX_RE",
    "INGREDIENT_SECTION_END_PATTERNS",
    "INGREDIENT_SINGLE_CHAR_KEEP_SET",
    "INGREDIENT_TEXT_LIMIT",
    "INGREDIENT_TOP_LEVEL_DELIMITERS",
    "INGREDIENT_VALID_TERM_RE",
    "INGREDIENT_WRAPPED_TOKEN_RE",
    "INLINE_INGREDIENT_LABEL_RE",
    "MANUFACTURER_GROUP_TOPICS",
    "MANUFACTURER_LINE_RE",
    "NOISE_LINE_RE",
    "NUTRITION_HEADER_RE",
    "OTHER_TOPIC_ORDER",
    "OTHER_TOPIC_PATTERNS",
    "OTHER_TOPIC_REGEX",
    "SPACE_RE",
    "TOPIC_TRIM_EDGE_RE",
]
