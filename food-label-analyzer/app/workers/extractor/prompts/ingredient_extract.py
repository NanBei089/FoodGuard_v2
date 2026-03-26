from __future__ import annotations


def build_ingredient_extract_prompt() -> str:
    return """你是配料表提取助手。只返回合法 JSON 数组，不要输出任何解释文字。

请从以下 OCR 文本中找出食品配料表，并将所有配料项展开为扁平字符串数组。
要求：
1. 保留原文顺序。
2. 括号中的子配料也要展开。
3. 如果找不到配料表，返回 []。

OCR 文本：
{full_raw_text}

返回格式示例：
["牛蹄筋", "白砂糖", "黄豆酱", "水", "大豆", "卡拉胶"]
"""


__all__ = ["build_ingredient_extract_prompt"]
