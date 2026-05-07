#!/usr/bin/env python3
"""
てらこAIニュースダイジェスト — 音声生成
edge-tts (Microsoft Neural voices) を使用。APIキー・費用不要。
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

REPO_DIR    = Path(__file__).parent
PODCAST_DIR = REPO_DIR / "podcast"

CATEGORIES_JA = {
    "model":    "モデル・リリース",
    "research": "研究・技術",
    "business": "ビジネス・産業",
    "policy":   "政策・倫理",
    "tools":    "ツール・開発",
}

WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

VOICE    = "ja-JP-NanamiNeural"
BASE_URL = "https://anomalocaress.github.io/ai-news-digest"


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    replacements = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&#8217;": "'", "&#8220;": "「", "&#8221;": "」",
        "&#8230;": "…", "\xa0": " ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()


def build_script(articles_by_category: Dict[str, List[Dict]], date: datetime) -> str:
    """
    ニュース読み上げ原稿を生成する。
    日本語フレーム + 英語タイトル/本文（NanamiNeural は英語も自然に発音）。
    """
    date_str = date.strftime("%Y年%m月%d日")
    weekday  = WEEKDAYS_JA[date.weekday()]
    total    = sum(len(v) for v in articles_by_category.values())

    lines: List[str] = []

    # ---- オープニング ----
    lines.append(
        f"てらこAIニュースダイジェスト。"
        f"{date_str}、{weekday}曜日版をお届けします。"
        f"本日は{total}件のAIニュースをピックアップしました。"
    )
    lines.append("")

    # ---- カテゴリ別 ----
    for category, cat_name in CATEGORIES_JA.items():
        articles = articles_by_category.get(category, [])
        if not articles:
            continue

        lines.append(f"■ {cat_name}、{len(articles)}件。")
        lines.append("")

        for i, article in enumerate(articles, 1):
            title   = clean_text(article.get("title_en") or article.get("title_ja") or "")
            summary = clean_text(article.get("summary") or "")
            source  = clean_text(article.get("source") or "")

            # 冗長なフォールバックテキストは省略
            if summary == "Read the full article for details.":
                summary = ""

            # 長すぎる本文は300文字で区切る（1記事あたり約30秒）
            if len(summary) > 300:
                summary = summary[:297] + "…"

            lines.append(f"{i}件目。{title}。")
            if source:
                lines.append(f"（{source}より）")
            if summary:
                lines.append(summary)
            lines.append("")

    # ---- クロージング ----
    lines.append(
        "以上、てらこAIニュースダイジェストでした。"
        "明日もAIの最新情報をお届けします。"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audio generation (edge-tts, async)
# ---------------------------------------------------------------------------

async def _generate_async(script: str, output_path: Path) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(script, VOICE)
    await communicate.save(str(output_path))


def _run(coro):
    """イベントループを安全に起動するヘルパー。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RSS feed
# ---------------------------------------------------------------------------

def update_feed(date: datetime, audio_file: Path) -> None:
    """episodes.json と feed.xml を更新する。"""
    PODCAST_DIR.mkdir(exist_ok=True)
    episodes_file = PODCAST_DIR / "episodes.json"

    episodes: List[Dict] = []
    if episodes_file.exists():
        try:
            episodes = json.loads(episodes_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    date_str  = date.strftime("%Y-%m-%d")
    audio_url = f"{BASE_URL}/podcast/{audio_file.name}"
    size_bytes = audio_file.stat().st_size

    episodes = [e for e in episodes if e.get("date") != date_str]
    episodes.insert(0, {
        "date":  date_str,
        "title": f"てらこAIニュースダイジェスト - {date_str}",
        "url":   audio_url,
        "size":  size_bytes,
    })
    episodes = episodes[:30]

    episodes_file.write_text(
        json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # feed.xml
    items_xml = ""
    for ep in episodes:
        items_xml += f"""
  <item>
    <title>{ep['title']}</title>
    <enclosure url="{ep['url']}" length="{ep.get('size', 0)}" type="audio/mpeg"/>
    <pubDate>{ep['date']}</pubDate>
    <guid isPermaLink="false">{ep['url']}</guid>
  </item>"""

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1_0.dtd">
<channel>
  <title>てらこAIニュースダイジェスト</title>
  <description>毎朝6時配信、AIの最新ニュースをお届けします。</description>
  <link>{BASE_URL}</link>
  <language>ja</language>
  <itunes:author>teraco-labo</itunes:author>
  <itunes:category text="Technology"/>
  {items_xml}
</channel>
</rss>"""

    (PODCAST_DIR / "feed.xml").write_text(feed_xml, encoding="utf-8")
    print(f"  ✓ RSS: {len(episodes)} episodes")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_podcast(articles_by_category: Dict[str, List[Dict]], date: datetime) -> bool:
    """generate_news.py の main() から呼ばれるメイン関数。"""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("⚠️  edge-tts not found. Run: pip install edge-tts")
        return False

    PODCAST_DIR.mkdir(exist_ok=True)
    date_str = date.strftime("%Y-%m-%d")

    # 1. 原稿
    print("  原稿を作成中...")
    script     = build_script(articles_by_category, date)
    char_count = len(script)
    est_min    = char_count // 250
    print(f"  原稿: {char_count} 文字 (推定約{est_min}分)")

    (PODCAST_DIR / f"script-{date_str}.txt").write_text(script, encoding="utf-8")

    # 2. 音声
    output_file = PODCAST_DIR / f"ai-news-{date_str}.mp3"
    print(f"  音声生成中 ({VOICE})…")
    _run(_generate_async(script, output_file))

    size_mb = output_file.stat().st_size / 1_048_576
    print(f"  ✓ {output_file.name} ({size_mb:.1f} MB)")

    # 3. RSS
    update_feed(date, output_file)

    return True


# ---------------------------------------------------------------------------
# ローカルテスト用
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    date = datetime.strptime(sys.argv[1], "%Y-%m-%d") if len(sys.argv) > 1 else datetime.now()
    test_data: Dict[str, List[Dict]] = {
        "model": [
            {"title_en": "OpenAI releases GPT-5 with improved reasoning",
             "summary": "OpenAI has released GPT-5, featuring major improvements in multi-step reasoning and coding tasks.",
             "source": "TechCrunch"},
        ],
        "business": [
            {"title_en": "Anthropic raises $50B at $900B valuation",
             "summary": "Anthropic is in talks to raise a new funding round that would value the AI safety company at $900 billion.",
             "source": "VentureBeat"},
        ],
    }
    success = generate_podcast(test_data, date)
    print("✅ Done" if success else "❌ Failed")
