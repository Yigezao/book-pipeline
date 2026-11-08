"""新建一本书：把 txt 清洗、切段，生成 books/<书名>/，并打印下一步给智能体的话。

用法：
    python tools/new_book.py "D:\\书\\某本书.txt"
    python tools/new_book.py "某本书.txt" --yes
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "tools" / "prepare.py"


def ask(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]：").strip()
    return value or default


def ask_choice(prompt: str, choices: dict[str, str], default: str) -> str:
    while True:
        value = input(f"{prompt} [{default}]：").strip() or default
        if value in choices:
            return choices[value]
        print("输入不对，请重来。")


def safe_name(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" ._")
    return name or "book"


def unique_dir(parent: Path, name: str) -> Path:
    target = parent / name
    index = 2
    while target.exists():
        target = parent / f"{name}-{index}"
        index += 1
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="新建一本书的目录（不调用模型）")
    parser.add_argument("input", nargs="?", default="", help="全文 txt 路径")
    parser.add_argument("--yes", action="store_true", help="全部用默认值，不提问")
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="未标注")
    parser.add_argument("--mode", default="", choices=("literary", "narrative", "expository"))
    parser.add_argument("--source-level", default="", choices=("A", "B", "C"))
    parser.add_argument("--spoiler-policy", default="", choices=("no_ending", "main_ending_ok"))
    parser.add_argument("--target-minutes", type=int, default=0)
    parser.add_argument("--cpm", type=float, default=300, help="口播速度，字/分钟；暂定 300")
    parser.add_argument("--background", default="", help="可选：background.md 路径；同目录有 background.md 会自动复制")
    parser.add_argument("--brand", default="听书一刻")
    parser.add_argument("--platform", default="通用视频平台")
    parser.add_argument("--opening-mode", default="spoken", choices=("card", "spoken", "none"))
    parser.add_argument("--ending-mode", default="both", choices=("both", "s6", "card", "none"))
    parser.add_argument("--next-episode", default="")
    parser.add_argument("--content-warning", default="")
    parser.add_argument("--content-warning-mode", default="description", choices=("spoken", "description", "none"))
    args = parser.parse_args()

    raw_input = args.input.strip()
    if not raw_input and not args.yes:
        raw_input = input("把 txt 拖进来，或粘贴完整路径：").strip().strip('"')
    if not raw_input:
        print("没有输入文件。")
        return 2
    source = Path(raw_input).expanduser().resolve()
    if not source.is_file():
        print(f"找不到文件：{source}")
        return 2

    title = args.title.strip() or source.stem
    if not args.yes and not args.title:
        title = ask("书名", title)
    author = args.author
    if not args.yes and args.author == "未标注":
        author = ask("作者", author)

    mode = args.mode
    if not mode:
        mode = "narrative"
        if not args.yes:
            mode = ask_choice("类型 1=文学 2=网文 3=非虚构", {"1": "literary", "2": "narrative", "3": "expository"}, "2")
    source_level = args.source_level
    if not source_level:
        source_level = "C"
        if not args.yes:
            source_level = ask_choice("来源 1=正版 2=授权 3=网上txt", {"1": "A", "2": "B", "3": "C"}, "3")
    spoiler = args.spoiler_policy
    if not spoiler:
        spoiler = "no_ending"
        if not args.yes:
            spoiler = ask_choice("剧透 1=不剧透结局 2=讲清结局", {"1": "no_ending", "2": "main_ending_ok"}, "1")
    minutes = args.target_minutes or 15
    if not args.yes and not args.target_minutes:
        minutes = int(ask("目标时长（分钟）", "15") or 15)
    brand = args.brand
    if not args.yes:
        brand = ask("账号名", brand)
    warning = args.content_warning
    if not args.yes:
        warning = ask("内容提示（可留空）", warning)

    target = unique_dir(ROOT / "books", safe_name(title))
    command = [
        sys.executable, str(PREPARE),
        "--input", str(source),
        "--out", str(target),
        "--title", title,
        "--author", author,
        "--mode", mode,
        "--source-level", source_level,
        "--spoiler-policy", spoiler,
        "--target-minutes", str(minutes),
        "--cpm", str(args.cpm),
        "--brand", brand,
        "--platform", args.platform,
        "--opening-mode", args.opening_mode,
        "--ending-mode", args.ending_mode,
        "--next-episode", args.next_episode,
        "--content-warning", warning,
        "--content-warning-mode", args.content_warning_mode,
    ]
    print("\n开始清洗、识别章节、切段…\n")
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode != 0 or not (target / "meta.json").is_file():
        print("\n生成失败，检查上面的报错。")
        return result.returncode or 1

    background = Path(args.background).expanduser().resolve() if args.background else source.parent / "background.md"
    if background.is_file():
        shutil.copy2(background, target / "background.md")
        print(f"  背景资料：已复制 {background.name}")
    else:
        print("  背景资料：没有 background.md；S2 只讲书内信息，不编作者生平")

    relative = target.relative_to(ROOT)
    print("\n目录已生成：")
    print(f"  {target}")
    print("\n下一步，把这句话发给写稿智能体：\n")
    print(f"  读 WORKFLOW.md，输入目录是 {relative}。先做 Step 1，写完停下。")
    print("\n检查命令：")
    print(f"  python tools/check.py --book \"{relative}\" --stage notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
