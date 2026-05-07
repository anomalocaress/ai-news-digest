#!/usr/bin/env python3

import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import subprocess
import requests
import xml.etree.ElementTree as ET

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

REPO_DIR = Path(__file__).parent

CATEGORIES = ["model", "research", "business", "policy", "tools"]
CATEGORIES_JA = {
    "model": "モデル",
    "research": "研究",
    "business": "ビジネス",
    "policy": "ポリシー",
    "tools": "ツール",
}
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def fetch_rss_news(date: datetime) -> List[Dict]:
    """Fetch AI news from free RSS feeds (no API key required)."""
    RSS_SOURCES = [
        ("TechCrunch AI",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("VentureBeat AI",  "https://venturebeat.com/category/ai/feed/"),
        ("The Verge AI",    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("Wired AI",        "https://www.wired.com/feed/tag/ai/latest/rss"),
        ("Ars Technica",    "https://feeds.arstechnica.com/arstechnica/index"),
    ]

    # Keywords to filter general feeds (Ars Technica etc.)
    AI_KEYWORDS = [
        "ai", "artificial intelligence", "machine learning", "llm", "gpt", "claude",
        "gemini", "openai", "anthropic", "neural", "deep learning", "generative",
        "chatbot", "language model", "llama", "mistral", "deepseek", "chatgpt",
    ]

    all_articles: List[Dict] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)"}

    for source_name, url in RSS_SOURCES:
        try:
            resp = requests.get(url, timeout=15, headers=headers)
            if resp.status_code != 200:
                print(f"⚠️  {source_name}: HTTP {resp.status_code}")
                continue

            root = ET.fromstring(resp.content)

            # Support both RSS 2.0 (<item>) and Atom (<entry>)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//atom:entry", ns)

            count = 0
            for item in items:
                title = (
                    item.findtext("title") or
                    item.findtext("atom:title", namespaces=ns) or ""
                ).strip()

                desc = (
                    item.findtext("description") or
                    item.findtext("atom:summary", namespaces=ns) or ""
                ).strip()
                # Strip HTML tags from description
                import re
                desc = re.sub(r"<[^>]+>", "", desc)[:300]

                link_elem = item.find("link")
                link = ""
                if link_elem is not None:
                    link = link_elem.text or link_elem.get("href", "")
                if not link:
                    link = item.findtext("atom:link", namespaces=ns) or ""

                pub = (
                    item.findtext("pubDate") or
                    item.findtext("atom:published", namespaces=ns) or ""
                )[:10]  # YYYY-MM-DD

                if not title or not link:
                    continue

                # AI relevance filter for general feeds
                text_lower = (title + " " + desc).lower()
                if source_name == "Ars Technica":
                    if not any(kw in text_lower for kw in AI_KEYWORDS):
                        continue

                all_articles.append({
                    "title": title,
                    "description": desc,
                    "source": {"name": source_name},
                    "publishedAt": pub,
                    "url": link,
                })
                count += 1
                if count >= 10:
                    break

            print(f"✓ {source_name}: {count} articles")

        except Exception as e:
            print(f"⚠️  {source_name}: {e}")

    # Deduplicate by normalised title prefix
    seen: set = set()
    unique: List[Dict] = []
    for a in all_articles:
        key = a["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    print(f"✓ Total: {len(unique)} unique articles from RSS")
    return unique[:40]


def categorize_by_keywords(title: str, description: str) -> str:
    """Keyword-based AI news categorization (no API required)."""
    text = ((title or "") + " " + (description or "")).lower()

    scores = {
        "model": sum(1 for kw in [
            "model", "gpt", "claude", "gemini", "llama", "mistral", "deepseek",
            "weights", "training", "fine-tuning", "parameter", "architecture",
            "transformer", "chatgpt", "copilot", "multimodal", "language model",
            "release", "launched", "announced new", "version",
        ] if kw in text),
        "research": sum(1 for kw in [
            "research", "paper", "study", "university", "findings", "discovers",
            "breakthrough", "arxiv", "benchmark", "dataset", "efficiency",
            "scientists", "published", "journal", "algorithm", "method",
        ] if kw in text),
        "business": sum(1 for kw in [
            "funding", "investment", "company", "startup", "acquisition",
            "partnership", "market", "revenue", "valuation", "billion", "million",
            "ceo", "ipo", "venture", "enterprise", "deal", "merger", "raises",
        ] if kw in text),
        "policy": sum(1 for kw in [
            "policy", "regulation", "government", "law", "ethics", "safety",
            "governance", "congress", "senate", "eu", "ban", "restriction",
            "rights", "privacy", "risk", "compliance", "act", "legislation",
        ] if kw in text),
        "tools": sum(1 for kw in [
            "tool", "platform", "api", "software", "plugin", "library",
            "framework", "sdk", "integration", "app", "feature", "update",
            "deploy", "open source", "github", "developer", "open-source",
        ] if kw in text),
    }

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "research"


def translate_ja(text: str) -> str:
    """Translate English text to Japanese using Google Translate public endpoint (no API key)."""
    if not text:
        return text
    try:
        resp = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ja", "dt": "t", "q": text},
            timeout=8,
        )
        data = resp.json()
        return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text  # fall back to original on error


def categorize_articles(articles: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize articles by keyword matching and translate to Japanese. No paid API."""
    result: Dict[str, List[Dict]] = {cat: [] for cat in CATEGORIES}

    for article in articles:
        title = article.get("title", "")
        description = article.get("description", "")
        source = article.get("source", {}).get("name", "Unknown")
        url = article.get("url", "")

        if not title or not url:
            continue

        category = categorize_by_keywords(title, description)

        title_ja = translate_ja(title)
        summary_ja = translate_ja(description[:250]) if description else "詳細は記事をご覧ください。"

        entry = {
            "category": category,
            "title_ja": title_ja,
            "title_en": title,
            "summary": summary_ja,
            "source": source,
            "date": article.get("publishedAt", "")[:10],
            "url": url,
            "importance": 2,
        }
        result[category].append(entry)
        print(f"✓ [{category}] {title_ja[:60]}")

    total = sum(len(v) for v in result.values())
    print(f"✓ {total} articles categorised")
    return result


def generate_html(articles_by_category: Dict[str, List[Dict]], target_date: datetime) -> str:
    """Generate HTML from articles (dict keyed by category)."""

    # Count articles per category
    category_counts = {cat: len(articles_by_category.get(cat, [])) for cat in CATEGORIES}

    # Filter out empty categories
    active_categories = {
        k: v for k, v in articles_by_category.items() if v
    }

    # Prepare template variables
    total_count = sum(category_counts.values())
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
        cat_display = CATEGORIES_JA.get(category, category.upper())

        articles_html += f'  <!-- {cat_display} -->\n'
        articles_html += f'  <div class="section-label" id="section-{category}">{cat_display}</div>\n'
        articles_html += f'  <div class="grid">\n\n'

        for article in cat_articles:
            importance = article.get("importance", 2)
            stars_html = ""
            for i in range(3):
                filled = "filled" if i < importance else ""
                stars_html += f'<div class="dot {filled}"></div>'

            articles_html += f'''    <article class="card {category}">
      <div class="card-top">
        <span class="card-label {category}">{CATEGORIES_JA.get(category, category.upper())}</span>
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
            cat_display = CATEGORIES_JA.get(category, category.upper())
            cat_bar_html += f'    <button class="cat-pill {category}" onclick="document.getElementById(\'section-{category}\').scrollIntoView({{behavior: \'smooth\'}});">● {cat_display} ({category_counts[category]})</button>\n'

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


def send_email_draft(email_html: str, target_date: datetime) -> bool:
    """Send email draft to user via Gmail API or SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_to = "fujisaki@teraco-labo.com"
    date_str = target_date.strftime("%Y年%m月%d日")

    try:
        # Try Gmail API first (for local/interactive mode)
        try:
            # Using Gmail MCP - only works in interactive sessions
            import requests
            gmail_api_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
            # This would require OAuth2 token setup
        except Exception:
            pass

        # Fallback: Use SMTP via Gmail
        gmail_user = os.getenv("GMAIL_ADDRESS")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

        if not gmail_user or not gmail_pass:
            print(f"⚠️  Gmail credentials not configured.")
            print(f"   Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD to enable email delivery.")
            return False

        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"てらこAIニュースダイジェスト - {date_str}"
        msg["From"] = gmail_user
        msg["To"] = email_to

        # Attach HTML content
        part = MIMEText(email_html, "html", "utf-8")
        msg.attach(part)

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [email_to], msg.as_string())

        print(f"✓ Email sent to: {email_to}")
        return True

    except smtplib.SMTPAuthenticationError:
        print(f"❌ Email auth failed: Invalid credentials")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ Email send error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def update_index_html(date: datetime):
    """Update index.html to redirect to latest digest (only if date is newer)."""
    import re as _re
    date_str = date.strftime("%Y-%m-%d")
    latest_file = f"ai-news-{date_str}.html"
    index_path = REPO_DIR / "index.html"

    # Check current redirect date — don't regress to an older date
    if index_path.exists():
        current = index_path.read_text(encoding="utf-8")
        m = _re.search(r"ai-news-(\d{4}-\d{2}-\d{2})\.html", current)
        if m and m.group(1) >= date_str:
            print(f"⏭  index.html already points to {m.group(1)} (≥ {date_str}), skipping")
            return

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

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"✓ Updated index.html → {latest_file}")


def build_email_html(categorized: Dict[str, List[Dict]], date: datetime, include_recommendations: bool = True) -> str:
    """Build HTML email content with styled articles."""
    date_str = date.strftime("%Y年%m月%d日")
    weekday = WEEKDAYS_JA[date.weekday()]

    # Import recommendation engine
    try:
        from recommendation_engine import analyze_user_preferences, generate_recommendations, add_recommendations_to_email
        use_recommendations = include_recommendations
    except:
        use_recommendations = False

    email_html = (
        """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: 'Hiragino Sans', 'Helvetica Neue', sans-serif; max-width: 600px; margin: 0; padding: 20px; background: #f5f5f5; }
  .container { background: white; border-radius: 8px; padding: 30px; }
  .header { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #60a5fa; padding: 20px; border-radius: 8px; margin-bottom: 30px; text-align: center; }
  .header h1 { margin: 0; font-size: 24px; }
  .header p { margin: 5px 0 0 0; font-size: 12px; color: #94a3b8; }
  .section { margin-bottom: 30px; }
  .section-title { font-size: 16px; font-weight: bold; color: #1e293b; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }
  .article { margin-bottom: 15px; padding: 12px; background: #f8fafc; border-left: 3px solid #60a5fa; border-radius: 4px; }
  .article-title { font-weight: bold; color: #1e293b; margin-bottom: 5px; font-size: 14px; }
  .article-summary { font-size: 13px; color: #475569; line-height: 1.5; margin-bottom: 5px; }
  .article-source { font-size: 11px; color: #64748b; }
  .footer { text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px; }
  .podcast-box { background: #f0f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
  .podcast-box h3 { margin: 0 0 10px 0; color: #1e293b; font-size: 14px; }
  .podcast-box a { color: #60a5fa; text-decoration: none; font-size: 12px; }
  .category-model { border-left-color: #1d4ed8; }
  .category-research { border-left-color: #6d28d9; }
  .category-business { border-left-color: #065f46; }
  .category-policy { border-left-color: #92400e; }
  .category-tools { border-left-color: #0e7490; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📰 AI News Digest</h1>
    <p>"""
        + date_str
        + """（"""
        + weekday
        + """）</p>
  </div>

  <p>おはようございます！</p>
  <p>てらこAIニュースダイジェスト、本日の最新情報をお届けします。</p>
"""
    )

    # Add articles by category
    category_colors = {
        "research": "#6d28d9",
        "business": "#065f46",
        "policy": "#92400e",
        "tools": "#0e7490"
    }

    for category in CATEGORIES:
        if category not in categorized or not categorized[category]:
            continue

        articles = categorized[category]
        cat_display = CATEGORIES_JA.get(category, category.upper())
        color = category_colors.get(category, "#1d4ed8")

        email_html += f'\n  <div class="section">\n    <div class="section-title">【{cat_display}】 ({len(articles)}件)</div>\n'

        for i, article in enumerate(articles, 1):
            title_ja = article.get('title_ja', '')
            summary = article.get('summary', '')[:150]
            source = article.get('source', 'Unknown')
            email_html += f'    <div class="article category-{category}">\n'
            email_html += f'      <div class="article-title">{i}. {title_ja}</div>\n'
            email_html += f'      <div class="article-summary">{summary}</div>\n'
            email_html += f'      <div class="article-source">{source}</div>\n'
            email_html += f'    </div>\n'

        email_html += "  </div>\n"

    # Add podcast section
    date_iso = date.strftime("%Y-%m-%d")
    audio_url = f"https://anomalocaress.github.io/ai-news-digest/podcast/ai-news-{date_iso}.mp3"
    email_html += '\n  <div class="podcast-box">\n'
    email_html += '    <h3>🎙️ 本日の音声ダイジェスト</h3>\n'
    email_html += f'    <p>全{sum(len(v) for v in categorized.values())}件のニュースを音声でお届けします。</p>\n'
    email_html += f'    <p style="margin:12px 0;">\n'
    email_html += f'      <a href="{audio_url}" style="background:#0f172a;color:#60a5fa;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold;">▶ 音声を再生する（MP3）</a>\n'
    email_html += f'    </p>\n'
    email_html += '    <p style="font-size:11px;color:#64748b;">\n'
    email_html += '      <a href="https://anomalocaress.github.io/ai-news-digest/podcast/feed.xml">📡 RSSフィード</a>\n'
    email_html += '    </p>\n'
    email_html += '  </div>\n\n'
    email_html += '  <div class="footer">\n'
    email_html += '    <p>AI News Digest | <a href="https://anomalocaress.github.io/ai-news-digest" style="color: #60a5fa; text-decoration: none;">https://anomalocaress.github.io/ai-news-digest</a></p>\n'
    email_html += '  </div>\n'
    email_html += '</div>\n'
    email_html += '</body>\n'
    email_html += '</html>'

    # Add recommendations if enabled
    if use_recommendations:
        try:
            user_analysis = analyze_user_preferences(categorized)
            recommendations = generate_recommendations(user_analysis)
            email_html = add_recommendations_to_email(email_html, recommendations)
        except Exception as e:
            print(f"⚠️  Recommendation engine error: {e}")

    return email_html


def save_email_html(email_html: str, date: datetime) -> Path:
    """Save email HTML to file for manual sending."""
    date_str = date.strftime("%Y-%m-%d")
    email_file = REPO_DIR / f".email-draft-{date_str}.html"

    with open(email_file, "w", encoding="utf-8") as f:
        f.write(email_html)

    return email_file


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

    # Step 1: Fetch articles from free RSS feeds
    print("\n1️⃣  Fetching articles from RSS feeds...")
    articles = fetch_rss_news(target_date)

    if not articles:
        print("❌ No articles fetched. Exiting.")
        return

    # Step 2: Categorize by keywords
    print("\n2️⃣  Categorizing articles...")
    categorized = categorize_articles(articles)

    total = sum(len(v) for v in categorized.values())
    if total == 0:
        print("❌ No articles successfully categorized. Exiting.")
        return

    # Step 3: Generate HTML
    print("\n3️⃣  Generating HTML...")
    html_content = generate_html(categorized, target_date)

    # Step 4: Save HTML
    output_file = save_html(html_content, target_date)

    # Step 5: Generate podcast (edge-tts, free)
    print("\n4️⃣  Generating podcast...")
    try:
        from generate_podcast import generate_podcast
        generate_podcast(categorized, target_date)
    except Exception as e:
        print(f"⚠️  Podcast generation error: {e}")

    # Step 6: Build and send email
    print("\n5️⃣  Building and sending email...")
    email_html = build_email_html(categorized, target_date)
    email_file = save_email_html(email_html, target_date)
    print(f"✓ Email draft saved: {email_file.name}")

    # Send email to user
    email_sent = send_email_draft(email_html, target_date)
    if not email_sent:
        print(f"⚠️  Email draft ready at: {email_file.name}")
        print(f"   Please configure GMAIL_ADDRESS and GMAIL_APP_PASSWORD for auto-sending.")

    # Step 7: Update index.html
    print("\n6️⃣  Updating index.html...")
    update_index_html(target_date)

    # Step 8: Commit and push
    if os.getenv("GITHUB_TOKEN"):
        print("\n7️⃣  Committing and pushing...")
        commit_and_push(target_date)
    else:
        print("\n⚠️  GITHUB_TOKEN not set. Skipping git operations.")

    print(f"\n✅ Success! Generated: {output_file.name}")


if __name__ == "__main__":
    main()
