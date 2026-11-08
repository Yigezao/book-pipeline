"""把 Get_book/Books 下的书导入 Book_Agent_Pipeline/books，生成当前格式。

用法：
    python tools/import_getbook.py --dry-run
    python tools/import_getbook.py
    python tools/import_getbook.py --cpm 300 --target-minutes 15

说明：
    - 只读 Get_book/Books/<n>_<书名>/{meta.json, source/original.txt}
    - 已存在同名书跳过，不覆盖
    - 统一按 literary、source-level C、15 分钟生成；可在参数里改
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "books"
PREPARE = ROOT / "tools" / "prepare.py"
DEFAULT_GETBOOK = Path(r"F:\Desktop\Study\#Project\Get_book\Books")


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" ._")
    return name or "book"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Get_book 批量导入书")
    parser.add_argument("--source-dir", default=str(DEFAULT_GETBOOK))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-minutes", type=float, default=15)
    parser.add_argument("--cpm", type=float, default=300,
                        help="口播速度，字/分钟；导入时按 300 字/分钟做预算")
    parser.add_argument("--source-level", default="C", choices=("A", "B", "C"))
    parser.add_argument("--mode", default="literary", choices=("literary", "narrative", "expository"),
                        help="默认按小说导入；非虚构书用 --mode expository")
    parser.add_argument("--brand", default="听书一刻")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        print(f"找不到 Get_book/Books：{source_dir}")
        return 2
    BOOKS.mkdir(parents=True, exist_ok=True)

    imported = []
    skipped = []
    failed = []
    folders = sorted([d for d in source_dir.iterdir() if d.is_dir()], key=lambda p: p.name)
    for folder in folders:
        meta_path = folder / "meta.json"
        source = folder / "source" / "original.txt"
        if not meta_path.is_file() or not source.is_file():
            skipped.append({"folder": folder.name, "reason": "缺 meta.json 或 original.txt"})
            continue
        try:
            source_meta = read_json(meta_path)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"folder": folder.name, "reason": f"meta 读不了：{exc}"})
            continue
        title = str(source_meta.get("title") or folder.name).strip()
        author = str(source_meta.get("author") or "未标注").strip()
        language = str(source_meta.get("language") or "")
        target = BOOKS / safe_name(title)
        if target.exists():
            skipped.append({"folder": folder.name, "title": title, "reason": "同名书已存在"})
            continue
        if args.dry_run:
            imported.append({"folder": folder.name, "title": title, "author": author,
                            "language": language, "target": str(target)})
            continue

        command = [
            sys.executable, str(PREPARE),
            "--input", str(source),
            "--out", str(target),
            "--title", title,
            "--author", author,
            "--mode", args.mode,
            "--source-level", args.source_level,
            "--target-minutes", str(args.target_minutes),
            "--cpm", str(args.cpm),
            "--brand", args.brand,
        ]
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0 or not (target / "meta.json").is_file():
            failed.append({"folder": folder.name, "title": title,
                           "error": (result.stderr or result.stdout or "")[-800:]})
            continue

        meta = read_json(target / "meta.json")
        meta.update({
            "language": language,
            "source_type": source_meta.get("source_type", ""),
            "source_url": source_meta.get("source", ""),
            "getbook_index": source_meta.get("catalog", {}).get("index"),
            "getbook_folder": folder.name,
            "getbook_sha256": source_meta.get("stats", {}).get("sha256", ""),
        })
        (target / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        imported.append({"folder": folder.name, "title": title, "author": author,
                         "language": language, "target": str(target)})
        print(f"[{len(imported)}] {title} / {author} ({language})")

    report = {
        "source_dir": str(source_dir),
        "dry_run": args.dry_run,
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }
    (BOOKS / "_import_getbook.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n导入：{} 本；跳过：{} 本；失败：{} 本".format(
        len(imported), len(skipped), len(failed)))
    if skipped:
        print("跳过：")
        for item in skipped:
            print(f"  - {item.get('title') or item['folder']}：{item['reason']}")
    if failed:
        print("失败：")
        for item in failed:
            print(f"  - {item.get('title') or item['folder']}：{item['error'].splitlines()[-1] if item['error'] else '未知'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
