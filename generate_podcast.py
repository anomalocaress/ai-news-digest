#!/usr/bin/env python3
"""
てらこAIニュースダイジェスト — 音声生成
edge-tts (Microsoft Neural voices) を使用。APIキー・費用不要。
"""

import asyncio
import json
import re
from datetime import datetime
from email.utils import formatdate
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
COVER_URL = f"{BASE_URL}/podcast/cover.jpg"
PODCAST_EMAIL = "fujisaki@teraco-labo.com"

# カテゴリごとの最大記事数（合計 12〜15 件程度）
MAX_PER_CATEGORY = {
    "model":    3,
    "research": 2,
    "business": 3,
    "policy":   2,
    "tools":    2,
}

# 記事間のつなぎフレーズ（ローテーション）
_TRANSITIONS = [
    "次のニュースです。",
    "続いてこちら。",
    "次のトピックです。",
    "もう一件ご紹介します。",
    "次のニュースに参ります。",
]

# ---------------------------------------------------------------------------
# TTS 発音改善：略語・固有名詞をカタカナに変換
# ---------------------------------------------------------------------------
_TTS_REPLACEMENTS = [
    ("ChatGPT",   "チャットジーピーティー"),
    ("GPT-4o",    "ジーピーティーフォーオー"),
    ("GPT-4",     "ジーピーティーフォー"),
    ("GPT-5.5",   "ジーピーティーファイブポイントファイブ"),
    ("GPT-5",     "ジーピーティーファイブ"),
    ("GPT-o3",    "ジーピーティーオースリー"),
    ("GPT-o4",    "ジーピーティーオーフォー"),
    ("GPT",       "ジーピーティー"),
    ("LLMs",      "エルエルエム"),
    ("LLM",       "エルエルエム"),
    ("xAI",       "エックスエーアイ"),
    ("OpenAI",    "オープンエーアイ"),
    ("AGI",       "エージーアイ"),
    ("APIs",      "エーピーアイ"),
    ("API",       "エーピーアイ"),
    ("DeepSeek",  "ディープシーク"),
    ("GitHub",    "ギットハブ"),
    ("AWS",       "エーダブリューエス"),
    ("TSMC",      "ティーエスエムシー"),
    ("SpaceX",    "スペースエックス"),
    ("CEO",       "シーイーオー"),
    ("CTO",       "シーティーオー"),
    ("CFO",       "シーエフオー"),
    ("IPO",       "アイピーオー"),
    ("EU",        "ヨーロッパ連合"),
    ("FCC",       "米国連邦通信委員会"),
    ("SDK",       "エスディーケー"),
    ("RLHF",      "アールエルエイチエフ"),
    ("SOTA",      "最先端"),
]


def preprocess_for_tts(text: str) -> str:
    """TTS 読み上げ用にテキストを前処理する。"""
    if not text:
        return text
    for pattern, replacement in _TTS_REPLACEMENTS:
        text = text.replace(pattern, replacement)
    # 英数字と日本語の境界にスペース挿入（NanamiNeural が自然に読むため）
    text = re.sub(r"([A-Za-z0-9])([ぁ-んァ-ン一-龯])", r"\1 \2", text)
    text = re.sub(r"([ぁ-んァ-ン一-龯])([A-Z])", r"\1 \2", text)
    return text


def clean_text(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    for k, v in {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
                 "&#8217;": "'", "&#8220;": "「", "&#8221;": "」",
                 "&#8230;": "…", "\xa0": " "}.items():
        text = text.replace(k, v)
    return text.strip()


# ---------------------------------------------------------------------------
# 重要記事の選定（カテゴリごとに上位 N 件）
# ---------------------------------------------------------------------------

def select_top_articles(articles_by_category: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    selected: Dict[str, List[Dict]] = {}
    for cat, articles in articles_by_category.items():
        max_n = MAX_PER_CATEGORY.get(cat, 2)
        sorted_arts = sorted(articles, key=lambda a: a.get("importance", 2), reverse=True)
        selected[cat] = sorted_arts[:max_n]
    return selected


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------

def build_script(articles_by_category: Dict[str, List[Dict]], date: datetime) -> str:
    date_str = date.strftime("%Y年%m月%d日")
    weekday  = WEEKDAYS_JA[date.weekday()]

    selected    = select_top_articles(articles_by_category)
    total       = sum(len(v) for v in selected.values())
    trans_index = 0

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
    first_in_category = True

    for category, cat_name in CATEGORIES_JA.items():
        articles = selected.get(category, [])
        if not articles:
            continue

        # カテゴリ見出し
        lines.append(f"■ {cat_name}のコーナーです。")
        lines.append("")
        first_in_category = True

        for article in articles:
            article_num += 1

            # ---- 記事間のつなぎ（最初の記事はスキップ）----
            if not first_in_category:
                transition = _TRANSITIONS[trans_index % len(_TRANSITIONS)]
                trans_index += 1
                lines.append(transition)
                lines.append("")
            first_in_category = False

            # フィールド取得・クリーニング
            title   = preprocess_for_tts(clean_text(
                article.get("title_ja") or article.get("title_en") or ""
            ))
            summary = preprocess_for_tts(clean_text(article.get("summary") or ""))
            source  = preprocess_for_tts(clean_text(article.get("source") or ""))

            if summary in ("Read the full article for details.", "詳細は記事をご覧ください。"):
                summary = ""

            # 番号＋タイトル
            title_clean = title.rstrip("。．.")
            lines.append(f"{article_num}つ目。{title_clean}。")

            if source:
                lines.append(f"（{source} より）")

            if summary:
                if len(summary) > 500:
                    summary = summary[:497] + "…"
                lines.append(summary)

            lines.append("")

        # カテゴリ間のブリッジ
        lines.append("")

    # ---- クロージング ----
    lines.append(
        f"以上、本日の注目 {total}件をお届けしました。"
        "てらこ エーアイ ニュースダイジェスト、また明日もお楽しみに。"
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
# RSS feed（Spotify / Apple Podcasts 対応フォーマット）
# ---------------------------------------------------------------------------

def _rfc2822(date_str: str) -> str:
    """'YYYY-MM-DD' → RFC 2822 形式（Spotify の pubDate に必要）。"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # 毎朝 JST 06:00 (= UTC 21:00 前日) に設定
        import calendar, time
        ts = calendar.timegm(dt.timetuple()) + 21 * 3600  # UTC 21:00 前日 → 簡易
        return formatdate(ts, usegmt=True)
    except Exception:
        return formatdate(usegmt=True)


def _hms(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def update_feed(date: datetime, audio_file: Path) -> None:
    """episodes.json と Spotify/Apple 対応 feed.xml を更新する。"""
    PODCAST_DIR.mkdir(exist_ok=True)
    episodes_file = PODCAST_DIR / "episodes.json"

    episodes: List[Dict] = []
    if episodes_file.exists():
        try:
            episodes = json.loads(episodes_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    date_str   = date.strftime("%Y-%m-%d")
    audio_url  = f"{BASE_URL}/podcast/{audio_file.name}"
    size_bytes = audio_file.stat().st_size
    # 32kbps MP3 として duration を概算
    duration_sec = size_bytes // 4000

    ep_num = len(episodes) + 1  # 既存エピソード数 + 1

    episodes = [e for e in episodes if e.get("date") != date_str]
    episodes.insert(0, {
        "date":        date_str,
        "title":       f"てらこAIニュースダイジェスト - {date_str}",
        "url":         audio_url,
        "size":        size_bytes,
        "duration":    duration_sec,
        "episode_num": ep_num,
    })
    episodes = episodes[:60]

    episodes_file.write_text(
        json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- feed.xml ----
    items_xml = ""
    for i, ep in enumerate(episodes):
        ep_ep_num = ep.get("episode_num", len(episodes) - i)
        dur_hms   = _hms(ep.get("duration", 0))
        pub       = _rfc2822(ep.get("date", ""))
        items_xml += f"""
  <item>
    <title>{ep['title']}</title>
    <itunes:title>{ep['title']}</itunes:title>
    <itunes:episode>{ep_ep_num}</itunes:episode>
    <itunes:episodeType>full</itunes:episodeType>
    <itunes:duration>{dur_hms}</itunes:duration>
    <itunes:explicit>false</itunes:explicit>
    <enclosure url="{ep['url']}" length="{ep.get('size', 0)}" type="audio/mpeg"/>
    <pubDate>{pub}</pubDate>
    <guid isPermaLink="false">{ep['url']}</guid>
  </item>"""

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1_0.dtd"
  xmlns:podcast="https://podcastindex.org/namespace/1.0">
<channel>
  <title>てらこAIニュースダイジェスト</title>
  <itunes:title>てらこAIニュースダイジェスト</itunes:title>
  <description>毎朝6時配信。AIの最新ニュースを厳選してわかりやすくお届けします。</description>
  <itunes:summary>毎朝6時配信。AIの最新ニュースを厳選してわかりやすくお届けします。</itunes:summary>
  <link>{BASE_URL}</link>
  <language>ja</language>
  <itunes:author>てらこAIニュースダイジェスト</itunes:author>
  <itunes:owner>
    <itunes:name>teraco-labo</itunes:name>
    <itunes:email>{PODCAST_EMAIL}</itunes:email>
  </itunes:owner>
  <itunes:image href="{COVER_URL}"/>
  <itunes:explicit>false</itunes:explicit>
  <itunes:type>episodic</itunes:type>
  <itunes:category text="Technology">
    <itunes:category text="Tech News"/>
  </itunes:category>
  {items_xml}
</channel>
</rss>"""

    (PODCAST_DIR / "feed.xml").write_text(feed_xml, encoding="utf-8")
    print(f"  ✓ RSS feed: {len(episodes)} episodes")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_podcast(articles_by_category: Dict[str, List[Dict]], date: datetime) -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("⚠️  edge-tts not found. Run: pip install edge-tts")
        return False

    PODCAST_DIR.mkdir(exist_ok=True)
    date_str = date.strftime("%Y-%m-%d")

    # 1. 原稿生成
    print("  原稿を作成中...")
    script     = build_script(articles_by_category, date)
    char_count = len(script)
    est_min    = char_count // 250
    print(f"  原稿: {char_count} 文字 (推定約{est_min}分)")

    script_file = PODCAST_DIR / f"script-{date_str}.txt"
    script_file.write_text(script, encoding="utf-8")

    # 2. 音声生成
    output_file = PODCAST_DIR / f"ai-news-{date_str}.mp3"
    print(f"  音声生成中 ({VOICE})…")
    _run(_generate_async(script, output_file))

    size_mb = output_file.stat().st_size / 1_048_576
    print(f"  ✓ {output_file.name} ({size_mb:.1f} MB)")
    print(f"  📁 ローカルパス: {output_file.resolve()}")
    print(f"  🌐 公開URL: {BASE_URL}/podcast/{output_file.name}")

    # 3. RSS 更新
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
             "summary": "オープンエーアイは、複数ステップの推論とコーディングタスクで大幅な改善を遂げた最新モデルを発表しました。従来比で推論精度が40%向上しており、医療診断や法律文書の解析にも活用できるとしています。",
             "source": "TechCrunch", "importance": 3},
        ],
        "business": [
            {"title_ja": "アンソロピック、評価額9000億ドルで新たな資金調達へ",
             "title_en": "Anthropic raises $50B at $900B valuation",
             "summary": "エーアイ安全企業のアンソロピックが、評価額9000億ドルで新たな資金調達ラウンドを検討していることが明らかになりました。",
             "source": "VentureBeat", "importance": 2},
        ],
    }
    success = generate_podcast(test_data, date)
    print("✅ Done" if success else "❌ Failed")
