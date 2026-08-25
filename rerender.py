#!/usr/bin/env python3
"""
公開済みダイジェストの再描画。

テンプレートや用語辞書を更新したとき、生成済みの号にも反映させるために使う。
記事の中身（選別結果・日本語）は既存の HTML から読み戻すため、
Claude の再呼び出しは発生しない（費用ゼロ・内容は変わらない）。

  python rerender.py 2026-08-25 2026-08-26
  python rerender.py --since 2026-08-25
"""

import html as _html
import re
import sys
from datetime import datetime
from pathlib import Path

import digest_page
import monetize
import social_kit

REPO_DIR = Path(__file__).parent


def _overview(raw: str) -> list:
    """既存ページから「今日の3行まとめ」を読み戻す（用語マークは除去する）。"""
    i = raw.find("lead-label")
    if i < 0:
        return []
    m = re.search(r"<ol>(.*?)</ol>", raw[i:], re.DOTALL)
    if not m:
        return []
    return [_html.unescape(re.sub(r"<.*?>", "", li)).strip()
            for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.DOTALL)]


def rerender(date_iso: str, verbose: bool = True) -> bool:
    path = REPO_DIR / f"ai-news-{date_iso}.html"
    if not path.exists():
        if verbose:
            print(f"⏭  {date_iso}: ファイルが見つかりません")
        return False

    raw = path.read_text(encoding="utf-8")
    categorized = social_kit.load_from_html(date_iso)
    total = sum(len(v) for v in categorized.values())
    if total == 0:
        if verbose:
            print(f"⏭  {date_iso}: 記事を読み取れませんでした（旧形式の可能性）")
        return False

    date = datetime.strptime(date_iso, "%Y-%m-%d")
    podcast_ok = (REPO_DIR / "podcast" / f"ai-news-{date_iso}.mp3").exists()

    html = digest_page.render(categorized, date, overview=_overview(raw),
                              podcast_available=podcast_ok)
    html = monetize.apply_to_digest(html, categorized, date)
    path.write_text(html, encoding="utf-8")

    if verbose:
        marks = len(set(re.findall(r'data-t="([a-z0-9-]+)"', html)))
        print(f"✓ {date_iso}: {total} 件 / 用語 {marks} 語 / 音声 {'あり' if podcast_ok else 'なし'}")
    return True


def main():
    args = sys.argv[1:]
    if "--since" in args:
        start = args[args.index("--since") + 1]
        dates = sorted(
            m.group(1)
            for p in REPO_DIR.glob("ai-news-*.html")
            for m in [re.match(r"ai-news-(\d{4}-\d{2}-\d{2})\.html$", p.name)]
            if m and m.group(1) >= start
        )
    else:
        dates = [a for a in args if re.match(r"^\d{4}-\d{2}-\d{2}$", a)]

    if not dates:
        print(__doc__)
        return
    ok = sum(rerender(d) for d in dates)
    print(f"\n再描画: {ok}/{len(dates)} 件")


if __name__ == "__main__":
    main()
