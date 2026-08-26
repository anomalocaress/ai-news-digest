#!/usr/bin/env python3
"""
ナレッジ蓄積 — 「読んで終わり」を「次の判断に効く」に変える。

## なぜ必要か

Claude はセッションが終わると、そこで話したことを忘れます。
「ブレイン教材を読ませたから覚えているのでは」と思われがちですが、そうではありません。
覚えているように見えるのは、**同じ会話の中にいる間だけ**です。

つまり知識を残す方法はひとつしかありません。**リポジトリのファイルに書くこと。**
このモジュールはそのための保管庫です。ここに入れた知見は、
`CLAUDE.md` 経由で毎回のセッション開始時に読み込まれ、以後の相談で使われます。

## 何を入れるか

イケハヤさん・テツメモさんのニュースレター、教材、自分の失敗など、
「次に何かを決めるときに効く」ものだけ。ニュースそのものは対象外です
（それは日次ダイジェストの仕事）。

## 公開リポジトリであることの注意

このリポジトリは公開されています。**有料教材やニュースレターの本文をそのまま貼らないこと。**
入れるのは自分の言葉に落とした要点だけ。取り込んだメール本文（knowledge/inbox/）は
.gitignore で除外してあり、コミットされません。

## 使い方

    python knowledge.py add --title "..." --summary "..." --source テツメモ
    python knowledge.py list                    # 一覧
    python knowledge.py search Skill            # 検索
    python knowledge.py report --since 7        # 直近7日の報告
    python knowledge.py build                   # INDEX.md を再生成
    python knowledge.py stats

一番ラクなのは Claude に話すことです（→ KNOWLEDGE.md）。
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_DIR = Path(__file__).parent
KNOWLEDGE_DIR = REPO_DIR / "knowledge"
STORE_FILE = KNOWLEDGE_DIR / "knowledge.json"
INDEX_FILE = KNOWLEDGE_DIR / "INDEX.md"
INBOX_DIR = KNOWLEDGE_DIR / "inbox"

JST = timezone(timedelta(hours=9))

# 情報の確からしさ。ニュースレターの断言をそのまま事実として扱わないための区別。
CONFIDENCE_LABEL = {
    "fact": "検証済み",
    "claim": "出典の主張",
    "opinion": "意見・体験",
}

INDEX_MAX_ENTRIES = 120  # 索引に個別掲載する上限（超えた分は件数だけ出す）


def today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ ストア

def load() -> Dict:
    if not STORE_FILE.exists():
        return {"version": 1, "updated": "", "entries": []}
    try:
        return json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  knowledge.json の読み込みに失敗: {e}")
        return {"version": 1, "updated": "", "entries": []}


def save(data: Dict):
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    data["updated"] = today()
    STORE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def entries(data: Optional[Dict] = None) -> List[Dict]:
    return (data if data is not None else load()).get("entries", [])


def _make_id(title: str, date: str) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"{date.replace('-', '')}-{digest}"


def _normalize(entry: Dict) -> Dict:
    """欠けたフィールドを埋める。手書きの JSON を流し込んでも壊れないように。"""
    date = str(entry.get("date") or today())[:10]
    source = entry.get("source") or {}
    if isinstance(source, str):
        source = {"name": source}
    return {
        "id": entry.get("id") or _make_id(str(entry.get("title", "")), date),
        "date": date,
        "title": str(entry.get("title", "")).strip(),
        "summary": str(entry.get("summary", "")).strip(),
        "takeaways": [str(t).strip() for t in (entry.get("takeaways") or []) if str(t).strip()],
        "apply": [str(a).strip() for a in (entry.get("apply") or []) if str(a).strip()],
        "tags": [str(t).strip() for t in (entry.get("tags") or []) if str(t).strip()],
        "confidence": entry.get("confidence") if entry.get("confidence") in CONFIDENCE_LABEL else "claim",
        "source": {
            "type": source.get("type", "manual"),      # newsletter / material / manual / web
            "name": source.get("name", ""),            # イケハヤ / テツメモ / 自分の失敗 …
            "title": source.get("title", ""),          # メールの件名など
            "ref": source.get("ref", ""),              # gmail:<messageId> など辿れる手がかり
            "published": str(source.get("published", ""))[:10],
        },
        "visibility": entry.get("visibility", "private"),  # サイトには一切出さない
    }


def _dedupe_key(entry: Dict) -> str:
    ref = entry["source"].get("ref", "")
    return ref if ref else entry["title"]


def add(entry: Dict, verbose: bool = True) -> Optional[Dict]:
    """1件追加する。同じ出典・同じタイトルのものは追加しない（重複防止）。"""
    normalized = _normalize(entry)
    if not normalized["title"]:
        if verbose:
            print("⚠️  title が空のため追加しませんでした")
        return None

    data = load()
    existing_keys = {_dedupe_key(e) for e in map(_normalize, data.get("entries", []))}
    if _dedupe_key(normalized) in existing_keys:
        if verbose:
            print(f"・スキップ（登録済み）: {normalized['title'][:50]}")
        return None

    data.setdefault("entries", []).append(normalized)
    save(data)
    if verbose:
        print(f"✓ 追加: {normalized['title'][:60]}  [{normalized['id']}]")
    return normalized


def add_many(items: List[Dict], verbose: bool = True) -> int:
    return sum(1 for item in items if add(item, verbose=verbose))


def has_ref(ref: str) -> bool:
    """この出典はもう蒸留済みか（取り込みの二重処理を防ぐ）。"""
    return any((e.get("source") or {}).get("ref") == ref for e in entries())


# ------------------------------------------------------------------ 検索・抽出

def search(query: str, limit: int = 20) -> List[Dict]:
    words = [w for w in re.split(r"\s+", query.strip()) if w]
    if not words:
        return []
    hits = []
    for entry in map(_normalize, entries()):
        haystack = " ".join([
            entry["title"], entry["summary"], " ".join(entry["takeaways"]),
            " ".join(entry["apply"]), " ".join(entry["tags"]), entry["source"]["name"],
        ]).lower()
        score = sum(1 for w in words if w.lower() in haystack)
        if score:
            hits.append((score, entry))
    hits.sort(key=lambda x: (-x[0], x[1]["date"]), reverse=False)
    hits.sort(key=lambda x: (-x[0], x[1]["date"]))
    return [e for _, e in hits[:limit]]


def since(days: int) -> List[Dict]:
    threshold = (datetime.now(JST) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [e for e in map(_normalize, entries()) if e["date"] >= threshold]


def by_tag() -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = {}
    for entry in map(_normalize, entries()):
        for tag in (entry["tags"] or ["未分類"]):
            grouped.setdefault(tag, []).append(entry)
    return dict(sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])))


# ------------------------------------------------------------------ 索引の生成

def _one_liner(entry: Dict) -> str:
    src = entry["source"]
    who = src["name"] or src["type"]
    when = (src["published"] or entry["date"])[5:].replace("-", "/")
    mark = CONFIDENCE_LABEL.get(entry["confidence"], "")
    line = f"- **{entry['title']}** — {entry['summary']}"
    line += f"\n  <small>{who} {when}・{mark}・`{entry['id']}`</small>"
    if entry["apply"]:
        line += "\n  → 応用: " + " / ".join(entry["apply"])
    return line


def build_index(verbose: bool = True) -> str:
    """INDEX.md を作り直す。Claude がセッション開始時に読むのはこのファイル。"""
    all_entries = sorted(map(_normalize, entries()), key=lambda e: e["date"], reverse=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# ナレッジ索引",
        "",
        "<!-- knowledge.py build が生成します。手で編集しても次回上書きされます。 -->",
        "",
        f"最終更新: {today()} ／ 全 {len(all_entries)} 件",
        "",
        "ここに入っているのは、**このプロジェクトの判断に効く知見**です。",
        "ニュースそのものは対象外（それは日次ダイジェストの役割）。",
        "各行の末尾は「出典 日付・確からしさ・ID」。`claim`（出典の主張）は",
        "検証されていない主張なので、事実として断言しないこと。",
        "",
    ]

    actionable = [e for e in all_entries if e["apply"]]
    if actionable:
        lines += ["## このプロジェクトに効くもの", ""]
        lines += [_one_liner(e) for e in actionable[:40]]
        lines += [""]

    lines += ["## タグ別", ""]
    for tag, group in by_tag().items():
        lines.append(f"### {tag}（{len(group)}件）")
        lines.append("")
        for entry in sorted(group, key=lambda e: e["date"], reverse=True)[:INDEX_MAX_ENTRIES]:
            lines.append(_one_liner(entry))
        lines.append("")

    if not all_entries:
        lines += [
            "まだ1件も入っていません。",
            "",
            "```bash",
            "python knowledge.py add --title \"...\" --summary \"...\" --source テツメモ",
            "```",
            "",
            "Claude に「これ覚えといて」と話すのが一番早い（→ KNOWLEDGE.md）。",
            "",
        ]

    lines += [
        "---",
        "",
        "全文と詳細は `knowledge/knowledge.json`。検索は `python knowledge.py search <語>`。",
        "",
    ]

    text = "\n".join(lines)
    INDEX_FILE.write_text(text, encoding="utf-8")
    if verbose:
        print(f"✓ {INDEX_FILE.relative_to(REPO_DIR)} を更新（{len(all_entries)}件）")
    return text


# ------------------------------------------------------------------ 報告

def report(days: int = 7) -> str:
    """「新しく蓄えたナレッジ」の報告文（Markdown）。"""
    recent = sorted(since(days), key=lambda e: e["date"], reverse=True)
    head = f"## ナレッジ報告（直近{days}日）\n\n"
    if not recent:
        return head + f"この{days}日で新しく記録したものはありません。\n"

    sources: Dict[str, int] = {}
    for entry in recent:
        sources[entry["source"]["name"] or "その他"] = sources.get(entry["source"]["name"] or "その他", 0) + 1
    summary = "・".join(f"{name} {count}件" for name, count in sorted(sources.items(), key=lambda kv: -kv[1]))

    out = [head.rstrip(), "", f"新しく {len(recent)} 件を記録しました（{summary}）。", ""]
    for entry in recent:
        src = entry["source"]
        out.append(f"### {entry['title']}")
        out.append("")
        out.append(f"{entry['summary']}")
        out.append("")
        if entry["takeaways"]:
            out += [f"- {t}" for t in entry["takeaways"]] + [""]
        if entry["apply"]:
            out.append("**このプロジェクトへの応用**: " + " / ".join(entry["apply"]))
            out.append("")
        meta = f"出典: {src['name']}"
        if src["title"]:
            meta += f"「{src['title'][:60]}」"
        if src["published"]:
            meta += f"（{src['published']}）"
        meta += f" ／ {CONFIDENCE_LABEL.get(entry['confidence'], '')}"
        out += [f"<small>{meta}</small>", ""]
    return "\n".join(out) + "\n"


def send_report_email(days: int = 7, to: str = "") -> bool:
    """報告をメールで送る。日次ダイジェストと同じアプリパスワードを使う。"""
    import smtplib
    from email.mime.text import MIMEText

    address = __import__("os").getenv("GMAIL_ADDRESS")
    password = __import__("os").getenv("GMAIL_APP_PASSWORD")
    if not address or not password:
        print("⚠️  GMAIL_ADDRESS / GMAIL_APP_PASSWORD が未設定のため送信をスキップします")
        return False

    recent = since(days)
    if not recent:
        print(f"   この{days}日で新しい知見が無いため、報告メールは送りません")
        return False

    body = report(days)
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = f"ナレッジ報告 {today()}（新しく {len(recent)} 件）"
    message["From"] = address
    message["To"] = to or address
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(address, password)
            server.send_message(message)
        print(f"✓ 報告メールを送信しました → {message['To']}")
        return True
    except Exception as e:
        print(f"⚠️  報告メールの送信に失敗: {e}")
        return False


def stats() -> Dict:
    all_entries = list(map(_normalize, entries()))
    sources: Dict[str, int] = {}
    for entry in all_entries:
        key = entry["source"]["name"] or entry["source"]["type"]
        sources[key] = sources.get(key, 0) + 1
    pending = len(list(INBOX_DIR.glob("*.md"))) if INBOX_DIR.exists() else 0
    return {
        "total": len(all_entries),
        "last_7_days": len(since(7)),
        "last_30_days": len(since(30)),
        "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
        "tags": {tag: len(group) for tag, group in by_tag().items()},
        "inbox_files": pending,
    }


# ------------------------------------------------------------------ CLI

def _print_entry(entry: Dict, full: bool = False):
    src = entry["source"]
    tags = ("#" + " #".join(entry["tags"])) if entry["tags"] else ""
    print(f"[{entry['date']}] {entry['title']}")
    print(f"    {entry['summary'][:160]}")
    if full and entry["takeaways"]:
        for takeaway in entry["takeaways"]:
            print(f"    - {takeaway}")
    if entry["apply"]:
        print(f"    → 応用: {' / '.join(entry['apply'])}")
    print(f"    {src['name'] or src['type']} ／ {CONFIDENCE_LABEL.get(entry['confidence'], '')} {tags}  [{entry['id']}]")
    print()


def main():
    parser = argparse.ArgumentParser(description="ナレッジ蓄積")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="1件追加する")
    p_add.add_argument("--title", required=False, default="")
    p_add.add_argument("--summary", default="")
    p_add.add_argument("--takeaway", action="append", default=[], help="学び（複数可）")
    p_add.add_argument("--apply", action="append", default=[], help="このプロジェクトへの応用（複数可）")
    p_add.add_argument("--tag", action="append", default=[])
    p_add.add_argument("--source", default="", help="出典の名前（イケハヤ / テツメモ など）")
    p_add.add_argument("--source-type", default="manual",
                       choices=["newsletter", "material", "manual", "web"])
    p_add.add_argument("--source-title", default="")
    p_add.add_argument("--ref", default="")
    p_add.add_argument("--published", default="")
    p_add.add_argument("--confidence", default="claim", choices=list(CONFIDENCE_LABEL))
    p_add.add_argument("--json", default="", help="JSON で渡す（'-' で標準入力）")

    p_list = sub.add_parser("list", help="一覧")
    p_list.add_argument("--tag", default="")
    p_list.add_argument("--source", default="")
    p_list.add_argument("--limit", type=int, default=30)
    p_list.add_argument("--full", action="store_true")

    p_search = sub.add_parser("search", help="検索")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--limit", type=int, default=20)

    p_report = sub.add_parser("report", help="新しく蓄えたナレッジの報告")
    p_report.add_argument("--since", type=int, default=7)
    p_report.add_argument("--email", action="store_true", help="報告をメールで送る")
    p_report.add_argument("--to", default="", help="宛先（既定は自分）")

    sub.add_parser("build", help="INDEX.md を再生成")
    sub.add_parser("stats", help="統計")

    args = parser.parse_args()

    if args.command == "add":
        if args.json:
            raw = sys.stdin.read() if args.json == "-" else args.json
            payload = json.loads(raw)
            items = payload if isinstance(payload, list) else [payload]
            count = add_many(items)
            print(f"\n{count} 件を追加しました。")
        else:
            if not args.title:
                print("⚠️  --title か --json のどちらかが必要です")
                return 1
            add({
                "title": args.title,
                "summary": args.summary,
                "takeaways": args.takeaway,
                "apply": args.apply,
                "tags": args.tag,
                "confidence": args.confidence,
                "source": {
                    "type": args.source_type, "name": args.source,
                    "title": args.source_title, "ref": args.ref,
                    "published": args.published,
                },
            })
        build_index()

    elif args.command == "list":
        rows = list(map(_normalize, entries()))
        if args.tag:
            rows = [e for e in rows if args.tag in e["tags"]]
        if args.source:
            rows = [e for e in rows if args.source in e["source"]["name"]]
        rows.sort(key=lambda e: e["date"], reverse=True)
        if not rows:
            print("該当なし。")
            return 0
        print(f"{len(rows)} 件\n")
        for entry in rows[:args.limit]:
            _print_entry(entry, full=args.full)

    elif args.command == "search":
        hits = search(" ".join(args.query), limit=args.limit)
        if not hits:
            print("該当なし。")
            return 0
        print(f"{len(hits)} 件ヒット\n")
        for entry in hits:
            _print_entry(entry, full=True)

    elif args.command == "report":
        if args.email:
            send_report_email(args.since, args.to)
        else:
            print(report(args.since))

    elif args.command == "build":
        build_index()

    elif args.command == "stats":
        info = stats()
        print(f"蓄積: {info['total']} 件（直近7日 {info['last_7_days']} 件 / 30日 {info['last_30_days']} 件）")
        print("出典別:")
        for name, count in info["sources"].items():
            print(f"  {name}: {count}")
        print("タグ別:")
        for tag, count in info["tags"].items():
            print(f"  {tag}: {count}")
        if info["inbox_files"]:
            print(f"\n未蒸留のメール: {info['inbox_files']} 件（python knowledge_ingest.py distill）")

    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
