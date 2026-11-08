"""把 final.txt 按段落切成每段不超过 500 字符的 txt，用分割线隔开。

规则：
    - 分割线不切割段落；一个段落只会完整落在某一个分区里。
    - 贪心装：能塞进当前分区就塞；下一段塞进去会超过 500 字符，就开新分区。
    - 字数按原始字符算：汉字、数字、标点、段落内空格和换行都算；分割线本身不算。
    - 如果一个段落本身就超过 500 字符，脚本报错，不硬切；请先把那段拆成更小的段落。

用法：
    python tools/split_500.py --book "books/羊脂球"
    python tools/split_500.py --input final.txt --output final_500.txt --limit 500
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def section_length(paragraphs: list[str]) -> int:
    """原始字符数：含段落内空格、换行和段落之间的空行。"""
    return len("\n\n".join(paragraphs))


def nonws_length(paragraphs: list[str]) -> int:
    return sum(1 for char in "\n\n".join(paragraphs) if not char.isspace())


def split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def pack(paragraphs: list[str], limit: int) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            raise ValueError(
                f"有一段 {len(paragraph)} 字符，超过 {limit} 字符；分割线不能切段落，请先把这段拆成更小的段落：\n"
                f"{paragraph[:80]}..."
            )
        if current and section_length(current + [paragraph]) > limit:
            sections.append(current)
            current = []
        current.append(paragraph)
    if current:
        sections.append(current)
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description="把 final.txt 按段落切成 500 字符以内")
    parser.add_argument("--book", default="", help="书目录，如 books/羊脂球")
    parser.add_argument("--input", default="", help="输入 txt；和 --book 二选一")
    parser.add_argument("--output", default="", help="输出 txt；默认同目录 final_500.txt")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--separator", default="=====")
    args = parser.parse_args()

    if args.book:
        book = Path(args.book)
        if not book.is_absolute():
            book = (ROOT / book).resolve()
        source = book / "final.txt"
        target = book / "final_500.txt"
    elif args.input:
        source = Path(args.input)
        target = Path(args.output) if args.output else source.with_name("final_500.txt")
    else:
        print("要给 --book 或 --input。")
        return 2

    if not source.is_file():
        print(f"找不到输入：{source}")
        return 2
    text = source.read_text(encoding="utf-8-sig")
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        print("final.txt 是空的。")
        return 2
    try:
        sections = pack(paragraphs, args.limit)
    except ValueError as exc:
        print(f"分段失败：{exc}")
        return 1

    output = f"\n\n{args.separator}\n\n".join("\n\n".join(section) for section in sections) + "\n"
    target.write_text(output, encoding="utf-8")
    raw_counts = [section_length(section) for section in sections]
    nonws_counts = [nonws_length(section) for section in sections]
    print(f"已写入：{target}")
    print(f"  {len(paragraphs)} 段 → {len(sections)} 个分区；"
          f"原始字符 {min(raw_counts)}–{max(raw_counts)}，非空白 {min(nonws_counts)}–{max(nonws_counts)}（上限 {args.limit}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
