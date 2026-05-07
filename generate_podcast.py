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

# カテゴリごとの最大記事数（合計 12〜15 件程度）
MAX_PER_CATEGORY = {
    "model":    3,
    "research": 2,
    "business": 3,
    "policy":   2,
    "tools":    2,
}

# ---------------------------------------------------------------------------
# TTS 発音改善：略語・固有名詞をカタカナに変換
# 長いパターンを先に処理する（部分マッチ防止）
# ---------------------------------------------------------------------------
_TTS_REPLACEMENTS = [
    # AI 系略語
    ("ChatGPT",         "チャットジーピーティー"),
    ("GPT-4o",          "ジーピーティーフォーオー"),
    ("GPT-4",           "ジーピーティーフォー"),
    ("GPT-5.5",         "ジーピーティーファイブポイントファイブ"),
    ("GPT-5",           "ジーピーティーファイブ"),
    ("GPT-o3",          "ジーピーティーオースリー"),
    ("GPT-o4",          "ジーピーティーオーフォー"),
    ("GPT",             "ジーピーティー"),
    ("LLM",             "エルエルエム"),
    ("LLMs",            "エルエルエム"),
    ("xAI",             "エックスエーアイ"),
    ("OpenAI",          "オープンエーアイ"),
    ("AGI",             "エージーアイ"),
    ("API",             "エーピーアイ"),
    ("APIs",            "エーピーアイ"),
    # 企業・サービス
    ("DeepSeek",        "ディープシーク"),
    ("GitHub",          "ギットハブ"),
    ("AWS",             "エーダブリューエス"),
    ("GCP",             "グーグルクラウド"),
    ("TSMC",            "ティーエスエムシー"),
    ("SpaceX",          "スペースエックス"),
    # 職位・組織
    ("CEO",             "シーイーオー"),
    ("CTO",             "シーティーオー"),
    ("CFO",             "シーエフオー"),
    ("IPO",             "アイピーオー"),
    ("EU",              "ヨーロッパ連合"),
    ("FCC",             "米国連邦通信委員会"),
    # その他
    ("SDK",             "エスディーケー"),
    ("IDE",             "アイディーイー"),
    ("RAG",             "ラグ"),
    ("RLHF",            "アールエルエイチエフ"),
    ("SFT",             "エスエフティー"),
    ("SOTA",            "最先端"),
    ("benchmark",       "ベンチマーク"),
    ("Benchmark",       "ベンチマーク"),
]


def preprocess_for_tts(text: str) -> str:
    """TTS 読み上げ用にテキストを前処理する。"""
    if not text:
        return text

    # 正規表現パターンと通常パターンを分けて処理
    for pattern, replacement in _TTS_REPLACEMENTS:
        if pattern.startswith("("):  # regex
            text = re.sub(pattern, replacement, text)
        else:
            text = text.replace(pattern, replacement)

    # 英数字と日本語の間に読点相当のスペースを挿入（NanamiNeural が自然に読むため）
    text = re.sub(r"([A-Za-z0-9])([ぁ-んァ-ン一-龯])", r"\1 \2", text)
    text = re.sub(r"([ぁ-んァ-ン一-龯])([A-Z])", r"\1 \2", text)

    return text


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


# ---------------------------------------------------------------------------
# 重要記事の選定（カテゴリごとに上位 N 件）
# ---------------------------------------------------------------------------

def select_top_articles(articles_by_category: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """各カテゴリから最大 N 件を選ぶ（合計 12〜15 件）。"""
    selected: Dict[str, List[Dict]] = {}
    for cat, articles in articles_by_category.items():
        max_n = MAX_PER_CATEGORY.get(cat, 2)
        # importance の降順→先着順
        sorted_arts = sorted(
            articles,
            key=lambda a: a.get("importance", 2),
            reverse=True,
        )
        selected[cat] = sorted_arts[:max_n]
    return selected


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------

def build_script(articles_by_category: Dict[str, List[Dict]], date: datetime) -> str:
    """
    ニュース読み上げ原稿を生成する。
    - 重要記事を厳選（12〜15 件）
    - 日本語タイトル使用
    - 内容を詳しく解説する自然な文体
    - TTS 用発音前処理済み
    """
    date_str = date.strftime("%Y年%m月%d日")
    weekday  = WEEKDAYS_JA[date.weekday()]

    selected = select_top_articles(articles_by_category)
    total    = sum(len(v) for v in selected.values())

    lines: List[str] = []

    # ---- オープニング ----
    lines.append(
        f"てらこ エーアイ ニュースダイジェスト。"
        f"{date_str}、{weekday}曜日版をお届けします。"
        f"本日は特に注目の{total}件をピックアップし、内容まで詳しく解説します。"
        f"ではさっそく参りましょう。"
    )
    lines.append("")

    article_num = 0

    # ---- カテゴリ別 ----
    for category, cat_name in CATEGORIES_JA.items():
        articles = selected.get(category, [])
        if not articles:
            continue

        lines.append(f"■ {cat_name}。")
        lines.append("")

        for article in articles:
            article_num += 1

            # 日本語タイトルを優先
            title = clean_text(
                article.get("title_ja") or article.get("title_en") or ""
            )
            summary = clean_text(article.get("summary") or "")
            source  = clean_text(article.get("source") or "")

            # フォールバックを除外
            if summary in ("Read the full article for details.", "詳細は記事をご覧ください。"):
                summary = ""

            # TTS 前処理
            title   = preprocess_for_tts(title)
            summary = preprocess_for_tts(summary)
            source  = preprocess_for_tts(source)

            # ---- 記事読み上げ ----
            # 番号＋タイトル（末尾が句点なら追加しない）
            title_clean = title.rstrip("。．.")
            lines.append(f"{article_num}つ目。{title_clean}。")

            # 出典
            if source:
                lines.append(f"（{source} より）")

            # 本文サマリー（最大500文字）
            if summary:
                if len(summary) > 500:
                    summary = summary[:497] + "…"
                lines.append(summary)

            # 重要度が高い場合は補足フレーズを追加
            importance = article.get("importance", 2)
            if importance >= 3 and summary:
                lines.append(
                    "この動向は、 エーアイ 業界全体に大きな影響を与える可能性があります。"
                )

            lines.append("")

    # ---- クロージング ----
    lines.append(
        f"以上、{total}件の注目ニュースをお届けしました。"
        "てらこ エーアイ ニュースダイジェスト、次回もお楽しみに。"
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
            {"title_ja": "オープンエーアイ、推論能力が向上した新モデルを発表",
             "title_en": "OpenAI releases GPT-5 with improved reasoning",
             "summary": "オープンエーアイは、複数ステップの推論とコーディングタスクで大幅な改善を遂げた最新モデルを発表しました。このモデルは従来比で推論精度が40%向上しており、医療診断や法律文書の解析にも活用できるとしています。",
             "source": "TechCrunch",
             "importance": 3},
        ],
        "business": [
            {"title_ja": "アンソロピック、評価額9000億ドルで新たな資金調達へ",
             "title_en": "Anthropic raises $50B at $900B valuation",
             "summary": "エーアイ安全企業のアンソロピックが、評価額9000億ドルで新たな資金調達ラウンドを検討していることが明らかになりました。",
             "source": "VentureBeat",
             "importance": 2},
        ],
    }
    success = generate_podcast(test_data, date)
    print("✅ Done" if success else "❌ Failed")
