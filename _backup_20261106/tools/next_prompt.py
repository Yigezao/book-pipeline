"""打印某一本书下一步该发给智能体的提示词。

用法：
    python tools/next_prompt.py --book books/羊脂球 --next
    python tools/next_prompt.py --book books/羊脂球 --step 2

--next 会根据已有文件判断：笔记 → 大纲 → 主体稿 → 审稿 → 发布。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_book(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def audit_status(book: Path) -> str:
    path = book / "audit.json"
    if not path.is_file():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8-sig")).get("status") or "")
    except Exception:  # noqa: BLE001
        return ""


def detect_step(book: Path) -> int | None:
    if not (book / "notes" / "beat_sheet.json").is_file():
        return 1
    if not (book / "outline.json").is_file():
        return 2
    if not (book / "draft.md").is_file():
        return 3
    if audit_status(book) != "pass":
        return 4
    if not (book / "final.txt").is_file() or not (book / "final_500.txt").is_file() or not (book / "publish.md").is_file():
        return 5
    return None


def book_mode_of(book: Path) -> str:
    path = book / "meta.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8-sig")).get("mode") or "")
    except Exception:  # noqa: BLE001
        return ""


def prompt_for_expository(step: int, rel: str) -> str:
    if step == 1:
        return f"""读 WORKFLOW.md 和 prompts/nf_01_beat_sheet.md。
只做这一本：{rel}。
读完 source/original.txt 再写 notes/beat_sheet.json；
书内事实必须挂 segment_id；公共常识可以写，但不许编具体数字/引语/人名细节；
写完跑 python tools/check.py --book {rel} --stage notes，
通过后汇报，然后停下。"""
    if step == 2:
        return f"""读 WORKFLOW.md 和 prompts/nf_02_outline.md。
只做这一本：{rel}。

先问我两件事：这期讲哪几章、目标多少分钟（默认 15）。
我回答后跑 python tools/set_target.py --book {rel} --minutes N。

读 notes/beat_sheet.json、background.md（如果有）、segments/index.jsonl，
写 outline.json：五段 S1–S5，one_thing 只写一件事；
必须写 action（听完做一件事）和 application（落到听众处境）；
S4 必须安排"书的边界和常见误读"。

写完跑 python tools/check.py --book {rel} --stage outline，
通过后汇报，然后停下。"""
    if step == 3:
        return f"""读 WORKFLOW.md 和 prompts/nf_03_draft.md。
只做这一本：{rel}。

读 source/original.txt、notes/beat_sheet.json、outline.json、background.md（如果有）。
写 draft.md，只写 S1–S5：
- S1 钩子结束处单独写一行 <!-- S1_END -->；
- 钩子里不要出现书名/作者/"今天讲"；
- 一期只讲一件事，不许变成章节复述；
- 允许迁移到听众处境，但推论不能伪装成"书里说"；
- S5 出现书名 + 至少两个核心概念，并写清本期动作和亲读钩子；
- 引文单句 ≤50 字，合计 ≤300 字；
- 不写品牌开场、内容提示、S6。

写完跑 python tools/check.py --book {rel} --stage draft，
通过后汇报，然后停下。"""
    if step == 4:
        return f"""新开一个会话。读 WORKFLOW.md 和 prompts/nf_04_audit.md。
你不是写稿智能体。只做 Step 4：审 {rel}/draft.md，写 audit.json。
不要读写稿会话的聊天记录，不要修改 draft.md。

先跑：python tools/check.py --book {rel} --stage draft

对照原文重点审：书内事实有没有编、推论有没有伪装成"书里说"、
迁移有没有扭曲原意、是不是一期讲了一件事、动作够不够具体、有没有亲读冲动。
有问题只给 patch（原句 + 替换句 + 理由），不重写全文。
证据不足给 revise 或 blocked，不要假装 pass。
审完汇报，然后停下。"""
    if step == 5:
        return f"""读 WORKFLOW.md 和 prompts/05_publish.md。
前提：{rel}/audit.json 的 status=pass。

先一次性问我 5 件事（给默认值）：账号名、下期、内容提示、开场、结尾。
然后写进 meta.json，拼 final.txt：
钩子（到 S1_END 之前）→ 品牌口播 → 内容提示 → S1_END 之后正文；删掉 S1_END。
跑 python tools/split_500.py --book {rel}；
写 publish.md；
跑 python tools/check.py --book {rel} --stage final；
汇报 final.txt、final_500.txt、publish.md、主体字数/估算时长，然后停下。"""
    return "这本已经走完 Step 1–5；检查 final.txt、final_500.txt、publish.md。"


def prompt_for(step: int, book: Path) -> str:
    rel = book.relative_to(ROOT).as_posix() if book.is_relative_to(ROOT) else book.as_posix()
    if book_mode_of(book) == "expository":
        return prompt_for_expository(step, rel)
    if step == 1:
        return f"""读 WORKFLOW.md 和 prompts/01_beat_sheet.md。
只做这一本：{rel}。
读完 source/original.txt 再写 notes/beat_sheet.json；
写完跑 python tools/check.py --book {rel} --stage notes，
通过后汇报，然后停下。
不要读其他书，不要用你记得的版本补情节。"""
    if step == 2:
        return f"""读 WORKFLOW.md 和 prompts/02_outline.md。
只做这一本：{rel}。

先问我：这期口播要多少分钟（默认 15）。
我回答后跑 python tools/set_target.py --book {rel} --minutes N。
如果我已经说过时长，直接用 meta，不重复问。

读 notes/beat_sheet.json、background.md（如果有）、segments/index.jsonl，
写 outline.json：S1–S5 完整，S6 只留 slot；
S2 包含背景 + 人物地图 + 一句话主线；
作者/创作/时代信息只能来自 background.md。

写完跑 python tools/check.py --book {rel} --stage outline，
通过后汇报，然后停下。"""
    if step == 3:
        return f"""读 WORKFLOW.md 和 prompts/03_draft.md。
只做这一本：{rel}。

读 source/original.txt、notes/beat_sheet.json、outline.json、background.md（如果有）。
写 draft.md，只写 S1–S5：
- S1 钩子结束处单独写一行 <!-- S1_END -->；
- opening_mode=spoken 时，钩子和 S2 不要重复书名/作者/“今天讲”；
- S2 先背景和人物地图，再讲故事；
- 每个转折讲清为什么；每 5 分钟左右一句小结；
- 最后一句出现书名 + 至少两个核心人物原名；
- 不写品牌开场、内容提示、S6。

写完跑 python tools/check.py --book {rel} --stage draft，
通过后汇报，然后停下。"""
    if step == 4:
        return f"""新开一个会话。读 WORKFLOW.md 和 prompts/04_audit.md。
你不是写稿智能体。只做 Step 4：审 {rel}/draft.md，写 audit.json。
不要读写稿会话的聊天记录，不要修改 draft.md。

先跑：python tools/check.py --book {rel} --stage draft

对照 source/original.txt 和 background.md 审核事实、背景、结构、人名、口播语体、剧透、听众理解。
有问题只给 patch（原句 + 替换句 + 理由），不重写全文。
证据不足给 revise 或 blocked，不要假装 pass。
审完汇报，然后停下。"""
    if step == 5:
        return f"""读 WORKFLOW.md 和 prompts/05_publish.md。
前提：{rel}/audit.json 的 status=pass。

先一次性问我 5 件事（给默认值）：账号名、下期、内容提示、开场、结尾。
然后写进 meta.json，拼 final.txt：
钩子（到 S1_END 之前）→ 品牌口播 → 内容提示 → S1_END 之后正文 → S6；删掉 S1_END。
跑 python tools/split_500.py --book {rel}；
写 publish.md；
跑 python tools/check.py --book {rel} --stage final；
汇报 final.txt、final_500.txt、publish.md、主体字数/估算时长，然后停下。"""
    return "这本已经走完 Step 1–5；检查 final.txt、final_500.txt、publish.md。"


def main() -> int:
    parser = argparse.ArgumentParser(description="打印下一本书/下一步的提示词")
    parser.add_argument("--book", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--next", action="store_true", help="按文件自动判断下一步")
    group.add_argument("--step", type=int, choices=(1, 2, 3, 4, 5))
    args = parser.parse_args()

    book = resolve_book(args.book)
    if not book.is_dir():
        print(f"找不到书目录：{book}")
        return 2
    step = args.step or (detect_step(book) if args.next else None)
    if step is None:
        step = detect_step(book)
    if step is None:
        print(f"{book.relative_to(ROOT) if book.is_relative_to(ROOT) else book}：Step 1–5 都已完成。")
        return 0
    print(f"# {book.relative_to(ROOT) if book.is_relative_to(ROOT) else book} · Step {step}\n")
    print(prompt_for(step, book))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
