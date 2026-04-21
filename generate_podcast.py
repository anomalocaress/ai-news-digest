#!/usr/bin/env python3
"""Podcast generation module for AI News Digest."""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from html import escape

REPO_DIR = Path(__file__).parent
PODCAST_DIR = REPO_DIR / "podcast"
BASE_URL = "https://anomalocaress.github.io/ai-news-digest"
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]
MAX_EPISODES = 30

CATEGORIES_JA = {
    "model": "モデル",
    "research": "研究",
    "business": "ビジネス",
    "policy": "ポリシー",
    "tools": "ツール",
}


def generate_podcast_script(articles: List[Dict], target_date: datetime) -> str:
    """Generate a podcast script using Claude API."""
    from anthropic import Anthropic
    claude = Anthropic()

    date_str = target_date.strftime("%Y年%m月%d日")
    weekday = WEEKDAYS_JA[target_date.weekday()]

    articles_text = ""
    for i, article in enumerate(articles[:10], 1):
        cat_ja = CATEGORIES_JA.get(article.get("category", ""), "")
        articles_text += f"{i}. 【{cat_ja}】{article.get('title_ja', '')}\n"
        summary = article.get("summary", "")
        if summary:
            articles_text += f"   {summary[:120]}\n"

    prompt = f"""あなたは日本のAIニュースポッドキャスト「AIニュースダイジェスト」のホストです。
今日（{date_str}・{weekday}曜日）のAIニュースを元に、自然で聴きやすいポッドキャストの台本を作成してください。

■ 今日のニュース一覧
{articles_text}

■ 台本の要件
- 全体で約5分間（日本語で1500〜2000文字程度）
- 話し言葉を使った自然な語り口（「〜ですね」「〜でしょうか」「〜というわけです」「〜ということで」等）
- 構成：オープニング → 主要ニュース紹介（3〜5本） → まとめ・クロージング
- リスナーへの語りかけあり（「皆さん」「いかがでしたでしょうか」等）
- 番組名「AIニュースダイジェスト」を最初と最後に言及

台本のみ出力してください。指示やメタ情報、見出し等は含めないでください。"""

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text.strip()


def generate_audio(script: str, output_path: Path) -> int:
    """Convert script to audio using OpenAI TTS. Returns file size in bytes."""
    from openai import OpenAI

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return 0

    client = OpenAI(api_key=openai_key)
    PODCAST_DIR.mkdir(exist_ok=True)

    # OpenAI TTS has a 4096 character limit per request
    truncated_script = script[:4000]

    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="coral",
        input=truncated_script,
        speed=1.1,
    )

    response.stream_to_file(str(output_path))
    return output_path.stat().st_size


def estimate_duration(file_size: int) -> str:
    """Estimate MP3 duration from file size assuming 128kbps."""
    seconds = int(file_size * 8 / 128000)
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def load_episodes() -> List[Dict]:
    """Load existing episodes from episodes.json."""
    episodes_path = PODCAST_DIR / "episodes.json"
    if episodes_path.exists():
        with open(episodes_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_episodes(episodes: List[Dict]):
    """Save episodes to episodes.json."""
    PODCAST_DIR.mkdir(exist_ok=True)
    episodes_path = PODCAST_DIR / "episodes.json"
    with open(episodes_path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)


def build_rss_xml(episodes: List[Dict]) -> str:
    """Build RSS feed XML string."""
    items_xml = ""
    for ep in episodes[:MAX_EPISODES]:
        items_xml += f"""    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(ep.get('description', ''))}</description>
      <pubDate>{ep['pub_date']}</pubDate>
      <enclosure url="{ep['url']}" type="audio/mpeg" length="{ep['length']}"/>
      <guid isPermaLink="true">{ep['url']}</guid>
      <itunes:duration>{ep.get('duration', '5:00')}</itunes:duration>
    </item>
"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>AIニュースダイジェスト</title>
    <description>毎日のAIニュースを5分間の音声でお届けするポッドキャスト。モデル・研究・ビジネス・ポリシー・ツールの5カテゴリをカバー。</description>
    <link>{BASE_URL}/</link>
    <language>ja</language>
    <copyright>AI News Digest</copyright>
    <itunes:author>AI News Digest</itunes:author>
    <itunes:summary>毎日のAIニュースを5分間の音声でお届けするポッドキャスト</itunes:summary>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
{items_xml}  </channel>
</rss>"""


def update_rss_feed(date: datetime, audio_filename: str, file_size: int, script: str) -> str:
    """Add new episode to RSS feed. Returns audio URL."""
    date_str = date.strftime("%Y年%m月%d日")
    weekday = WEEKDAYS_JA[date.weekday()]
    pub_date = date.strftime("%a, %d %b %Y 21:00:00 +0000")

    audio_url = f"{BASE_URL}/podcast/{audio_filename}"
    episode = {
        "title": f"AIニュースダイジェスト - {date_str}（{weekday}）",
        "description": script[:500] + "...",
        "pub_date": pub_date,
        "url": audio_url,
        "length": file_size,
        "duration": estimate_duration(file_size),
        "date": date.strftime("%Y-%m-%d"),
    }

    episodes = load_episodes()
    episodes = [ep for ep in episodes if ep.get("date") != episode["date"]]
    episodes.insert(0, episode)
    episodes = episodes[:MAX_EPISODES]

    save_episodes(episodes)

    xml_content = build_rss_xml(episodes)
    feed_path = PODCAST_DIR / "feed.xml"
    PODCAST_DIR.mkdir(exist_ok=True)
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"  ✓ RSS feed: {len(episodes)} episodes total")
    return audio_url


def cleanup_old_mp3s():
    """Remove MP3 files for episodes beyond MAX_EPISODES."""
    episodes = load_episodes()
    if len(episodes) <= MAX_EPISODES:
        return

    old_episodes = episodes[MAX_EPISODES:]
    for ep in old_episodes:
        date_str = ep.get("date", "")
        if date_str:
            mp3_path = PODCAST_DIR / f"ai-news-{date_str}.mp3"
            if mp3_path.exists():
                mp3_path.unlink()
                print(f"  Removed old MP3: {mp3_path.name}")


def generate_podcast(articles: List[Dict], target_date: datetime) -> bool:
    """Main podcast generation function. Returns True if successful."""
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set. Skipping podcast generation.")
        return False

    print("\n🎙️  Generating podcast...")

    # Step 1: Generate script with Claude
    print("  Generating script with Claude...")
    try:
        script = generate_podcast_script(articles, target_date)
        print(f"  ✓ Script generated ({len(script)} chars)")
    except Exception as e:
        print(f"  ❌ Script generation failed: {e}")
        return False

    # Step 2: Generate audio with OpenAI TTS
    date_str = target_date.strftime("%Y-%m-%d")
    audio_filename = f"ai-news-{date_str}.mp3"
    audio_path = PODCAST_DIR / audio_filename

    print("  Generating audio with OpenAI TTS...")
    try:
        file_size = generate_audio(script, audio_path)
        if file_size == 0:
            print("  ❌ Audio generation skipped (no API key)")
            return False
        duration = estimate_duration(file_size)
        print(f"  ✓ Audio generated ({file_size / 1024 / 1024:.1f} MB, ~{duration})")
    except Exception as e:
        print(f"  ❌ Audio generation failed: {e}")
        return False

    # Step 3: Update RSS feed
    print("  Updating RSS feed...")
    try:
        audio_url = update_rss_feed(target_date, audio_filename, file_size, script)
    except Exception as e:
        print(f"  ❌ RSS update failed: {e}")
        return False

    # Step 4: Cleanup old MP3s
    cleanup_old_mp3s()

    print(f"\n✅ Podcast ready!")
    print(f"   Audio: {audio_url}")
    print(f"   RSS Feed: {BASE_URL}/podcast/feed.xml")

    return True


if __name__ == "__main__":
    # Test with fallback articles
    from datetime import datetime
    test_articles = [
        {
            "category": "model",
            "title_ja": "OpenAI が GPT-5 を発表",
            "summary": "OpenAIが新しい大規模言語モデルGPT-5を発表。前モデルより大幅な性能向上を達成。",
            "source": "TechCrunch",
        },
        {
            "category": "research",
            "title_ja": "DeepMindが強化学習で新記録",
            "summary": "Google DeepMindが強化学習の新アルゴリズムを開発し、複数のベンチマークで最高性能を達成。",
            "source": "Nature",
        },
    ]
    generate_podcast(test_articles, datetime.now())
