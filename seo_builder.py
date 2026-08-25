#!/usr/bin/env python3
"""
集客基盤ビルダー — 検索エンジン・SNS・RSS リーダーからの流入導線をつくる。

生成物:
  index.html   … トップページ（最新号＋アーカイブ一覧＋収益枠）
  archive.html … 全バックナンバー一覧
  sitemap.xml  … Google Search Console 用
  feed.xml     … サイト全体の RSS（ポッドキャストの podcast/feed.xml とは別物）
  robots.txt   … クロール許可＋サイトマップ告知

なぜこれが最初に必要か:
  収益枠をいくら貼っても、読まれなければ 0 円。
  これまでの index.html は最新号への meta refresh リダイレクトのみで、
  100本以上あるダイジェストは検索エンジンからほぼ見えない状態だった。

単体でも実行できる:  python seo_builder.py
"""

import re
import html as _html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import article_builder
import monetize
import site_theme

JST = timezone(timedelta(hours=9))
REPO_DIR = Path(__file__).parent
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

_COUNT_RE = re.compile(r'<div class="header-count">(\d+) articles</div>')


def collect_issues() -> List[Dict]:
    """公開済みダイジェストを新しい順に列挙する。"""
    issues = []
    for path in REPO_DIR.glob("ai-news-*.html"):
        m = re.match(r"ai-news-(\d{4}-\d{2}-\d{2})\.html$", path.name)
        if not m:
            continue
        date_iso = m.group(1)
        try:
            dt = datetime.strptime(date_iso, "%Y-%m-%d")
        except ValueError:
            continue

        count = 0
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:8000]
            cm = _COUNT_RE.search(head)
            if cm:
                count = int(cm.group(1))
        except Exception:
            pass

        issues.append({
            "date_iso": date_iso,
            "dt": dt,
            "file": path.name,
            "count": count,
            "label": f"{dt.year}年{dt.month}月{dt.day}日（{WEEKDAYS_JA[dt.weekday()]}）",
            "podcast": (REPO_DIR / "podcast" / f"ai-news-{date_iso}.mp3").exists(),
        })

    issues.sort(key=lambda x: x["date_iso"], reverse=True)
    return issues


# ---------------------------------------------------------------- ページ生成

def build_home(issues: List[Dict], articles: List[Dict], config: Dict) -> str:
    site = config.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    pod_base = config.get("podcast", {}).get("base_url", base).rstrip("/")
    name = site.get("name", "AI News Digest")

    head = monetize.build_head_tags(
        config,
        page_url=f"{base}/" if base else "",
        title=f"{name} | AI最新ニュースを毎朝6時に日本語で",
        description=site.get("description", ""),
    ).replace('<meta property="og:type" content="article">',
              '<meta property="og:type" content="website">')

    latest = issues[0] if issues else None
    hero_actions = ""
    if latest:
        hero_actions += f'      <a class="btn btn-primary" href="{latest["file"]}">最新号を読む（{latest["label"]}）</a>\n'
    hero_actions += '      <a class="btn btn-ghost" href="archive.html">バックナンバー</a>\n'
    if pod_base:
        hero_actions += f'      <a class="btn btn-ghost" href="{pod_base}/podcast/feed.xml">🎧 ポッドキャスト</a>\n'
    hero_actions += '      <a class="btn btn-ghost" href="feed.xml">📡 RSS</a>\n'

    recent = issues[:12]
    cards = ""
    for it in recent:
        meta = f'{it["count"]} 記事' if it["count"] else "ダイジェスト"
        if it["podcast"]:
            meta += " · 🎧 音声あり"
        cards += (
            f'    <a class="issue" href="{it["file"]}">\n'
            f'      <div class="d">{_html.escape(it["label"])}</div>\n'
            f'      <div class="m">{meta}</div>\n'
            "    </a>\n"
        )

    reads = ""
    if articles:
        cards = "".join(
            f'    <a class="issue" href="articles/{a["file"]}">\n'
            f'      <div class="d">{_html.escape(a["title"])}</div>\n'
            f'      <div class="m">{_html.escape(a.get("description", "")[:70])}</div>\n'
            "    </a>\n"
            for a in articles[:6]
        )
        reads = (
            '  <div class="section-label">読み物</div>\n'
            f'  <div class="issue-grid">\n{cards}  </div>\n'
            '  <p style="margin-top:1rem;font-size:0.85rem;">'
            '<a href="articles/" style="color:var(--accent);font-weight:600;">解説記事の一覧を見る →</a></p>\n'
        )

    offers = monetize.render_offer_block(
        monetize.select_offers(config, None, datetime.now(JST).replace(tzinfo=None),
                               int(config.get("slots", {}).get("home_offers", 0))),
        heading="AIを学ぶ・仕事にする",
    )

    body = f"""<div class="hero">
  <div class="hero-inner">
    <h1>{_html.escape(name)}</h1>
    <p>{_html.escape(site.get("tagline", ""))}</p>
    <p style="font-size:0.85rem;margin-top:0.75rem;">{_html.escape(site.get("description", ""))}</p>
    <div class="hero-actions">
{hero_actions}    </div>
  </div>
</div>

<main>
{monetize.render_disclosure(config)}
{reads}
  <div class="section-label">最近のダイジェスト</div>
  <div class="issue-grid">
{cards}  </div>
{offers}{monetize.render_cta(config)}
  <div class="section-label">アーカイブ</div>
  <p style="font-size:0.85rem;color:var(--text-muted);">
    これまでに <strong>{len(issues)}</strong> 号を配信しました。
    <a href="archive.html" style="color:var(--accent);font-weight:600;">全バックナンバーを見る →</a>
  </p>
</main>

<footer>
  <strong>{_html.escape(name)}</strong> — {_html.escape(site.get("author", ""))}<br>
  毎朝6時に自動生成・自動配信しています。
  {site_theme.footer_links(config)}
</footer>"""

    return site_theme.page_shell(f"{name} | AI最新ニュースを毎朝6時に日本語で", head, body)


def build_archive(issues: List[Dict], config: Dict) -> str:
    site = config.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    name = site.get("name", "AI News Digest")

    head = monetize.build_head_tags(
        config,
        page_url=f"{base}/archive.html" if base else "",
        title=f"バックナンバー一覧 | {name}",
        description=f"{name} のバックナンバー全{len(issues)}号の一覧。日付ごとにAIニュースの日本語まとめを読めます。",
    ).replace('<meta property="og:type" content="article">',
              '<meta property="og:type" content="website">')

    by_month: Dict[str, List[Dict]] = {}
    for it in issues:
        by_month.setdefault(it["date_iso"][:7], []).append(it)

    sections = ""
    for month in sorted(by_month, reverse=True):
        y, m = month.split("-")
        sections += f'  <div class="section-label">{y}年{int(m)}月</div>\n  <ul class="issue-list">\n'
        for it in by_month[month]:
            meta = f'{it["count"]}記事' if it["count"] else ""
            if it["podcast"]:
                meta = (meta + " 🎧").strip()
            sections += (
                f'    <li><a href="{it["file"]}">{_html.escape(it["label"])}</a>'
                f'<span class="m">{meta}</span></li>\n'
            )
        sections += "  </ul>\n"

    body = f"""<div class="hero">
  <div class="hero-inner">
    <h1>バックナンバー</h1>
    <p>{_html.escape(name)} 全 {len(issues)} 号</p>
    <div class="hero-actions">
      <a class="btn btn-ghost" href="./">トップへ戻る</a>
    </div>
  </div>
</div>

<main>
{monetize.render_disclosure(config)}
{sections}
</main>

<footer>
  <strong>{_html.escape(name)}</strong> — {_html.escape(site.get("author", ""))}
  {site_theme.footer_links(config)}
</footer>"""

    return site_theme.page_shell(f"バックナンバー一覧 | {name}", head, body)


def build_about(config: Dict) -> str:
    """運営者情報・免責事項・プライバシーポリシー。

    広告を掲載する以上これは飾りではなく、
    「購入後の問い合わせ先はどこか」を読者に対して明示する実務上の線引きになる。
    ASP の審査でも提示を求められることが多い。
    """
    legal = config.get("legal", {})
    if not legal.get("enabled"):
        return ""

    site = config.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    name = site.get("name", "")
    ga = site.get("_ga_placeholder", "")

    head = monetize.build_head_tags(
        config,
        page_url=f"{base}/about.html" if base else "",
        title=f"運営者情報・免責事項 | {name}",
        description=f"{name} の運営者情報、広告掲載についての表示、免責事項、プライバシーポリシーです。",
    ).replace('<meta property="og:type" content="article">',
              '<meta property="og:type" content="website">')
    head = head.replace('<meta name="robots" content="index, follow, max-image-preview:large">',
                        '<meta name="robots" content="noindex, follow">')

    contact = site.get("contact_email", "")
    contact_html = (f'<a href="mailto:{_html.escape(contact)}">{_html.escape(contact)}</a>'
                    if contact else "（準備中）")
    parent_html = ""
    if site.get("parent_site_url"):
        parent_html = (f'<dt>運営元</dt><dd><a href="{_html.escape(site["parent_site_url"])}">'
                       f'{_html.escape(site.get("parent_site_name", ""))}</a></dd>')

    analytics_note = ""
    if monetize._filled(config.get("analytics", {}).get("ga4_measurement_id")):
        analytics_note = (
            "<p>本サイトでは、アクセス状況の把握のために Google Analytics を利用しています。"
            "この際、トラフィックデータの収集のために Cookie を使用しますが、個人を特定する情報は含まれません。"
            "Cookie の受け取りはブラウザの設定で拒否できます。</p>"
        )

    ad_note = (
        "<p>本サイトは、A8.net をはじめとするアフィリエイトプログラムに参加しています。"
        "記事内で紹介している商品・サービスのリンクを経由してお申し込みがあった場合、"
        "運営者が提供元から紹介料を受け取ることがあります。</p>"
        "<p>この紹介料はサービス提供元が負担するもので、"
        "読者の皆さまのお支払い金額が通常より高くなることは一切ありません。</p>"
        "<p>紹介する商品・サービスは運営者の判断で選んでおり、"
        "ニュース記事の収集・要約・掲載順は広告主の影響を受けません。</p>"
    )

    body = f"""<div class="hero">
  <div class="hero-inner">
    <div class="crumbs"><a href="./">{_html.escape(name)}</a></div>
    <h1>運営者情報・免責事項</h1>
    <p>広告の掲載方針と、お問い合わせ先の切り分けについて記載しています。</p>
  </div>
</div>

<main>
  <div class="legal">
    <h2>運営者情報</h2>
    <dl>
      <dt>サイト名</dt><dd>{_html.escape(name)}</dd>
      <dt>運営者</dt><dd>{_html.escape(site.get("operator", site.get("author", "")))}</dd>
      {parent_html}
      <dt>連絡先</dt><dd>{contact_html}</dd>
    </dl>

    <h2>広告掲載について</h2>
    {ad_note}

    <h2>免責事項</h2>
    <div class="strong-note">
      <p>{_html.escape(legal.get("disclaimer", ""))}</p>
    </div>
    <p>本サイトに掲載する情報は、掲載時点で正確を期すよう努めていますが、
    その完全性・正確性・最新性を保証するものではありません。
    掲載内容を利用したことにより生じた損害について、運営者は責任を負いかねます。
    サービスの料金・条件は変更されることがありますので、
    お申し込みの前に必ず提供元の公式サイトで最新の情報をご確認ください。</p>

    <h2>ニュース記事の引用について</h2>
    <p>本サイトのダイジェストは、各報道機関が公開している記事の見出しと要約、
    および出典元へのリンクを掲載しています。本文の全文転載は行っていません。
    掲載内容について権利者の方からご連絡をいただいた場合は、速やかに対応いたします。</p>

    <h2>プライバシーポリシー</h2>
    {analytics_note}
    <p>本サイトでは、お問い合わせをいただいた場合を除き、
    個人情報を収集することはありません。取得した個人情報は、
    お問い合わせへの返信以外の目的では利用せず、第三者に提供することもありません。</p>
    <p>アフィリエイトプログラムの提供元が、成果の計測のために Cookie を使用する場合があります。
    この場合も、運営者が個人を特定できる情報を取得することはありません。</p>
  </div>
</main>

<footer>
  <strong>{_html.escape(name)}</strong> — {_html.escape(site.get("author", ""))}
  {site_theme.footer_links(config)}
</footer>"""

    return site_theme.page_shell(f"運営者情報・免責事項 | {name}", head, body,
                                 extra_css=site_theme.LEGAL_CSS)


# ---------------------------------------------------------------- 機械向け出力

def build_sitemap(issues: List[Dict], articles: List[Dict], config: Dict) -> str:
    base = config.get("site", {}).get("base_url", "").rstrip("/")
    if not base:
        return ""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    urls = [
        f"  <url><loc>{base}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{base}/archive.html</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>",
    ]
    if config.get("legal", {}).get("enabled"):
        urls.append(
            f"  <url><loc>{base}/about.html</loc><lastmod>{today}</lastmod>"
            f"<changefreq>yearly</changefreq><priority>0.2</priority></url>"
        )
    if articles:
        urls.append(
            f"  <url><loc>{base}/articles/</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )
    for a in articles:
        # 解説記事は検索流入の本命なので優先度を高く設定する
        urls.append(
            f"  <url><loc>{base}/articles/{a['file']}</loc>"
            f"<lastmod>{a.get('updated') or today}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.9</priority></url>"
        )
    for it in issues:
        urls.append(
            f"  <url><loc>{base}/{it['file']}</loc><lastmod>{it['date_iso']}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.6</priority></url>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def build_feed(issues: List[Dict], articles: List[Dict], config: Dict, limit: int = 30) -> str:
    site = config.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    if not base:
        return ""
    name = site.get("name", "AI News Digest")
    items = ""
    for a in articles:
        try:
            adt = datetime.strptime(a.get("published", ""), "%Y-%m-%d").replace(hour=9, tzinfo=JST)
        except ValueError:
            continue
        items += f"""  <item>
    <title>{_html.escape(a['title'])}</title>
    <link>{base}/articles/{a['file']}</link>
    <guid isPermaLink="true">{base}/articles/{a['file']}</guid>
    <description>{_html.escape(a.get('description', ''))}</description>
    <pubDate>{adt.strftime('%a, %d %b %Y %H:%M:%S +0900')}</pubDate>
  </item>
"""
    for it in issues[:limit]:
        pub = it["dt"].replace(hour=6, tzinfo=JST).strftime("%a, %d %b %Y %H:%M:%S +0900")
        desc = f'{it["label"]}のAIニュースまとめ' + (f'（{it["count"]}記事）' if it["count"] else "")
        items += f"""  <item>
    <title>{_html.escape(f'AI最新ニュースまとめ {it["label"]}')}</title>
    <link>{base}/{it['file']}</link>
    <guid isPermaLink="true">{base}/{it['file']}</guid>
    <description>{_html.escape(desc)}</description>
    <pubDate>{pub}</pubDate>
  </item>
"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{_html.escape(name)}</title>
  <link>{base}/</link>
  <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
  <description>{_html.escape(site.get('description', ''))}</description>
  <language>ja</language>
{items}</channel>
</rss>
"""


def build_robots(config: Dict) -> str:
    base = config.get("site", {}).get("base_url", "").rstrip("/")
    lines = ["User-agent: *", "Allow: /", ""]
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- エントリポイント

def build_all(verbose: bool = True) -> Dict[str, int]:
    config = monetize.load_config()
    issues = collect_issues()
    # 解説記事を先にビルドしてから、トップ・サイトマップ・RSS に反映する
    articles = article_builder.build_all(verbose=verbose)
    written = {}

    outputs = {
        "index.html": build_home(issues, articles, config),
        "archive.html": build_archive(issues, config),
        "about.html": build_about(config),
        "sitemap.xml": build_sitemap(issues, articles, config),
        "feed.xml": build_feed(issues, articles, config),
        "robots.txt": build_robots(config),
    }
    for filename, content in outputs.items():
        if not content:
            if verbose:
                print(f"⏭  {filename} はスキップ（site.base_url が未設定）")
            continue
        (REPO_DIR / filename).write_text(content, encoding="utf-8")
        written[filename] = len(content)
        if verbose:
            print(f"✓ {filename} ({len(content):,} bytes)")

    if verbose:
        print(f"✓ 収録号数: {len(issues)} / 解説記事: {len(articles)}")
    return written


if __name__ == "__main__":
    build_all()
