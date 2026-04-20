#!/usr/bin/env python3

import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import subprocess
import requests
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
from anthropic import Anthropic



# Load environment variables
load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
REPO_DIR = Path(__file__).parent

# Initialize Anthropic client
client = Anthropic()

CATEGORIES = ["model", "research", "business", "policy", "tools"]
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def fetch_ai_news(date: datetime) -> List[Dict]:
    """Fetch AI news from News API for a given date."""
    if not NEWS_API_KEY:
        print("⚠️  NEWS_API_KEY not set. Using fallback data.")
        return generate_fallback_articles(date)

    # Search for AI-related news from the past 24 hours
    url = "https://newsapi.org/v2/everything"
    search_query = "(artificial intelligence OR machine learning OR LLM OR GPT OR Claude OR AI model) AND -bitcoin -crypto"

    params = {
        "q": search_query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 40,
        "apiKey": NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data["status"] != "ok":
            print(f"⚠️  News API error: {data.get('message', 'Unknown error')}")
            return generate_fallback_articles(date)

        articles = data.get("articles", [])
        print(f"✓ Fetched {len(articles)} articles from News API")

        # Filter out duplicates and low-quality articles
        seen_titles = set()
        unique_articles = []
        for article in articles:
            title = article.get("title", "").strip()
            if title and title not in seen_titles and len(title) > 20:
                seen_titles.add(title)
                unique_articles.append(article)

        return unique_articles[:30]  # Return top 30

    except Exception as e:
        print(f"❌ Error fetching from News API: {e}")
        return generate_fallback_articles(date)


def generate_fallback_articles(date: datetime) -> List[Dict]:
    """Generate fallback articles for testing."""
    return [
        {
            "title": "OpenAI Announces New GPT-5 Model",
            "description": "Major breakthrough in LLM performance",
            "source": {"name": "TechCrunch"},
            "publishedAt": date.isoformat(),
            "url": "https://techcrunch.com/example",
        },
        {
            "title": "Google DeepMind Discovers New AI Capabilities",
            "description": "Research breakthrough in reinforcement learning",
            "source": {"name": "Nature"},
            "publishedAt": date.isoformat(),
            "url": "https://nature.com/example",
        },
    ]


def simple_categorize(title: str, description: str) -> str:
    """Simple keyword-based categorization as fallback."""
    text = ((title or "") + " " + (description or "")).lower()

    model_keywords = ["model", "release", "announced", "gpt", "claude", "llm", "training", "weights"]
    research_keywords = ["research", "study", "paper", "university", "findings", "discovers", "breakthrough", "efficiency"]
    business_keywords = ["funding", "investment", "company", "startup", "acquisition", "partnership", "market"]
    policy_keywords = ["policy", "regulation", "government", "law", "ethics", "safety", "governance"]
    tools_keywords = ["tool", "platform", "api", "software", "benchmark", "dataset", "library"]

    scores = {
        "model": sum(1 for kw in model_keywords if kw in text),
        "research": sum(1 for kw in research_keywords if kw in text),
        "business": sum(1 for kw in business_keywords if kw in text),
        "policy": sum(1 for kw in policy_keywords if kw in text),
        "tools": sum(1 for kw in tools_keywords if kw in text),
    }

    return max(scores, key=scores.get) or "research"


def categorize_articles_with_claude(articles: List[Dict]) -> List[Dict]:
    """Use Claude to categorize articles and generate Japanese summaries."""
    if not articles:
        return []

    processed = []

    for article in articles:
        title = article.get("title", "")
        description = article.get("description", "")
        source = article.get("source", {}).get("name", "Unknown")
        pub_date = article.get("publishedAt", "")[:10]  # YYYY-MM-DD
        url = article.get("url", "")

        # Skip articles with missing critical info
        if not title or not url:
            continue

        # Use Claude to categorize and create summary if API key is set
        if CLAUDE_API_KEY:
            try:
                prompt = f"""以下のニュース記事を分析してください。

タイトル: {title}
説明: {description}

以下のカテゴリのいずれかに分類してください: model, research, business, policy, tools

JSON形式で返してください:
{{
  "category": "...",
  "title_ja": "日本語タイトル（30-50文字程度）",
  "title_en": "Original English Title",
  "summary": "日本語での説明文（150-200文字程度）",
  "importance": 2
}}

importance は 1-3 の整数です（3が最も重要）。"""

                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )

                response_text = message.content[0].text

                # Parse JSON from Claude response
                try:
                    json_start = response_text.find("{")
                    json_end = response_text.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_text[json_start:json_end]
                        parsed = json.loads(json_str)

                        # Validate and add to processed list
                        if parsed.get("category") in CATEGORIES:
                            parsed["source"] = source
                            parsed["date"] = pub_date
                            parsed["url"] = url
                            parsed.setdefault("importance", 2)
                            processed.append(parsed)
                            print(f"✓ Categorized: {parsed['title_ja']}")
                            continue
                except json.JSONDecodeError:
                    pass

            except Exception as e:
                print(f"⚠️  Claude API error for '{title}': {e}")

        # Fallback: Use simple keyword-based categorization
        category = simple_categorize(title, description)

        # Generate Japanese title and summary (simple approach)
        title_en = title[:60]
        title_ja = f"AI {title_en}"[:50]
        summary = description[:200] if description else "新しいAI技術に関するニュース"

        parsed = {
            "category": category,
            "title_ja": title_ja,
            "title_en": title_en,
            "summary": summary,
            "source": source,
            "date": pub_date,
            "url": url,
            "importance": 2,
        }
        processed.append(parsed)
        print(f"✓ Auto-categorized ({category}): {title_ja}")

    return processed


def generate_html(articles: List[Dict], target_date: datetime) -> str:
    """Generate HTML from articles using Jinja2 template."""

    # Organize articles by category
    articles_by_category = {cat: [] for cat in CATEGORIES}
    for article in articles:
        cat = article.get("category", "research")
        if cat in articles_by_category:
            articles_by_category[cat].append(article)

    # Count articles per category
    category_counts = {cat: len(articles_by_category[cat]) for cat in CATEGORIES}

    # Filter out empty categories
    active_categories = {
        k: v for k, v in articles_by_category.items() if v
    }

    # Prepare template variables
    total_count = len(articles)
    weekday = WEEKDAYS_JA[target_date.weekday()]
    date_str = target_date.strftime("%Y年%m月%d日")
    date_iso = target_date.strftime("%Y-%m-%d")

    # Read template HTML
    template_path = REPO_DIR / "ai-news-2026-04-13.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Simple template substitution (not using Jinja2 for full file)
    # We'll inject articles into the template by replacing placeholders

    # Build articles HTML
    articles_html = ""

    for category in CATEGORIES:
        if not active_categories.get(category):
            continue

        cat_articles = active_categories[category]
        cat_display = category.upper()

        articles_html += f'  <!-- {cat_display} -->\n'
        articles_html += f'  <div class="section-label">{cat_display}</div>\n'
        articles_html += f'  <div class="grid">\n\n'

        for article in cat_articles:
            importance = article.get("importance", 2)
            stars_html = ""
            for i in range(3):
                filled = "filled" if i < importance else ""
                stars_html += f'<div class="dot {filled}"></div>'

            articles_html += f'''    <article class="card {category}">
      <div class="card-top">
        <span class="card-label {category}">{cat_display}</span>
        <div class="stars">
          {stars_html}
        </div>
      </div>
      <div class="card-title-ja">{article.get('title_ja', '')}</div>
      <div class="card-title-en">{article.get('title_en', '')}</div>
      <div class="card-source">{article.get('source', 'Unknown')} · {article.get('date', date_iso)}</div>
      <div class="card-body">{article.get('summary', '')}</div>
      <a class="card-link {category}" href="{article.get('url', '#')}" target="_blank" rel="noopener">Read more →</a>
    </article>

'''

        articles_html += f'  </div>\n\n'

    # Build category bar
    cat_bar_html = ""
    for category in CATEGORIES:
        if category_counts[category] > 0:
            cat_display = category.upper()
            cat_bar_html += f'    <span class="cat-pill {category}">● {cat_display} ({category_counts[category]})</span>\n'

    # Replace placeholders in template
    html_output = template_content

    # Replace header date
    html_output = html_output.replace(
        '<div class="header-date">2026年4月13日（月）</div>',
        f'<div class="header-date">{date_str}（{weekday}）</div>',
    )

    # Replace article count
    html_output = html_output.replace(
        '<div class="header-count">12 articles</div>',
        f'<div class="header-count">{total_count} articles</div>',
    )

    # Replace title in <title> tag
    html_output = html_output.replace(
        '<title>AI News Digest — 2026.04.13</title>',
        f'<title>AI News Digest — {date_iso}</title>',
    )

    # Replace category bar
    start_marker = '  <div class="cat-bar-inner">\n'
    end_marker = '  </div>\n</div>\n\n<main>'

    start_idx = html_output.find(start_marker)
    end_idx = html_output.find(end_marker)

    if start_idx >= 0 and end_idx >= 0:
        before = html_output[:start_idx + len(start_marker)]
        after = html_output[end_idx:]
        html_output = before + cat_bar_html + after

    # Replace main content (articles)
    main_start = html_output.find('<main>\n\n  <!-- ')
    footer_start = html_output.find('\n</main>\n\n<footer>')

    if main_start >= 0 and footer_start >= 0:
        before = html_output[:main_start + 6]  # len('<main>')
        after = html_output[footer_start:]
        html_output = before + "\n\n" + articles_html + after

    return html_output


def save_html(html_content: str, date: datetime) -> Path:
    """Save HTML to file."""
    date_str = date.strftime("%Y-%m-%d")
    output_file = REPO_DIR / f"ai-news-{date_str}.html"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✓ Saved: {output_file}")
    return output_file


def update_index_html(date: datetime):
    """Update index.html to redirect to latest digest."""
    date_str = date.strftime("%Y-%m-%d")
    latest_file = f"ai-news-{date_str}.html"

    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="0; url={latest_file}">
  <title>AI News Digest</title>
</head>
<body>
  Redirecting to <a href="{latest_file}">latest digest</a>...
</body>
</html>
"""

    index_path = REPO_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"✓ Updated index.html → {latest_file}")


def commit_and_push(date: datetime):
    """Commit and push changes to GitHub."""
    date_str = date.strftime("%Y-%m-%d")

    try:
        os.chdir(REPO_DIR)

        # Git operations
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: AI News Digest {date_str}"],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "push"], check=True, capture_output=True)

        print(f"✓ Git push completed")

    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git error: {e.stderr.decode()}")


def main():
    """Main execution."""
    # Parse command line arguments
    target_date = datetime.now()
    if len(sys.argv) > 2 and sys.argv[1] == "--date":
        try:
            target_date = datetime.strptime(sys.argv[2], "%Y-%m-%d")
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)

    print(f"\n📰 Generating AI News Digest for {target_date.strftime('%Y-%m-%d')}")

    # Step 1: Fetch articles
    print("\n1️⃣  Fetching articles from News API...")
    articles = fetch_ai_news(target_date)

    if not articles:
        print("❌ No articles fetched. Exiting.")
        return

    # Step 2: Categorize with Claude
    print("\n2️⃣  Categorizing articles with Claude...")
    categorized = categorize_articles_with_claude(articles)

    if not categorized:
        print("❌ No articles successfully categorized. Exiting.")
        return

    print(f"✓ {len(categorized)} articles ready")

    # Step 3: Generate HTML
    print("\n3️⃣  Generating HTML...")
    html_content = generate_html(categorized, target_date)

    # Step 4: Save HTML
    output_file = save_html(html_content, target_date)

    # Step 5: Update index.html
    print("\n4️⃣  Updating index.html...")
    update_index_html(target_date)

    # Step 6: Commit and push
    if os.getenv("GITHUB_TOKEN"):
        print("\n5️⃣  Committing and pushing...")
        commit_and_push(target_date)
    else:
        print("\n⚠️  GITHUB_TOKEN not set. Skipping git operations.")

    print(f"\n✅ Success! Generated: {output_file.name}")


if __name__ == "__main__":
    main()
