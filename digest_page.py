#!/usr/bin/env python3
"""
日次ダイジェストのページ生成。

旧実装は 2026-04-13 の HTML を読み込んで文字列置換していたため、
構造が固定され、記事が何件あっても同じグリッドに敷き詰められていた。
50件のカードが平列で並び、どこから読めばいいのか分からない状態だった。

作り直した方針:
  - 冒頭に「今日の3行まとめ」を置き、ここだけ読めば済むようにする
  - カテゴリ順ではなく **重要度順** に並べる
  - 重要度3の記事は大きく扱い、視覚的に優先度を示す
  - サイト全体（トップ・読み物）と同じデザインに統一する

social_kit.py が過去号を解析して SNS 投稿文を作るため、
card / card-title-ja / card-source / card-body / dot filled といった
クラス名と出現順は旧実装から変えていない。
"""

import html as _html
from datetime import datetime
from typing import Dict, List, Optional

import monetize
import site_theme

CATEGORIES = ["model", "research", "business", "policy", "tools"]
CATEGORIES_JA = {
    "model": "モデル", "research": "研究", "business": "ビジネス",
    "policy": "ポリシー", "tools": "ツール",
}
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

DIGEST_CSS = """
  :root {
    --model:#1d4ed8; --research:#6d28d9; --business:#065f46;
    --policy:#92400e; --tools:#0e7490;
  }
  .lead { max-width:760px; margin:0 auto 2.5rem; padding:1.5rem 1.7rem;
    background:var(--card-bg); border:1px solid var(--border); border-radius:8px; }
  .lead-label { font-size:0.7rem; font-weight:700; letter-spacing:0.14em;
    color:var(--text-muted); margin-bottom:0.9rem; }
  .lead ol { list-style:none; counter-reset:lead; display:flex; flex-direction:column; gap:0.7rem; }
  .lead li { counter-increment:lead; position:relative; padding-left:1.9rem;
    font-size:0.95rem; line-height:1.85; }
  .lead li::before { content:counter(lead); position:absolute; left:0; top:0.3em;
    width:1.25rem; height:1.25rem; border-radius:50%; background:var(--accent); color:#fff;
    font-size:0.68rem; font-weight:700; display:flex; align-items:center; justify-content:center; }
  .digest { max-width:760px; margin:0 auto; display:flex; flex-direction:column; gap:1rem; }
  .card { padding:1.4rem 1.5rem; background:var(--card-bg); border:1px solid var(--border);
    border-left:3px solid var(--text-muted); border-radius:8px; }
  .card.model{border-left-color:var(--model)} .card.research{border-left-color:var(--research)}
  .card.business{border-left-color:var(--business)} .card.policy{border-left-color:var(--policy)}
  .card.tools{border-left-color:var(--tools)}
  .card-top { display:flex; align-items:center; gap:0.6rem; margin-bottom:0.6rem; }
  .card-label { font-size:0.66rem; font-weight:700; letter-spacing:0.06em; padding:2px 7px;
    border-radius:3px; color:#fff; background:var(--text-muted); }
  .card-label.model{background:var(--model)} .card-label.research{background:var(--research)}
  .card-label.business{background:var(--business)} .card-label.policy{background:var(--policy)}
  .card-label.tools{background:var(--tools)}
  .stars { display:flex; gap:3px; }
  .dot { width:6px; height:6px; border-radius:50%; background:var(--border); }
  .dot.filled { background:var(--text-muted); }
  .card-title-ja { font-size:1.08rem; font-weight:700; line-height:1.6; }
  .card-title-en { margin-top:0.25rem; font-size:0.78rem; color:var(--text-muted); line-height:1.5; }
  .card-source { margin-top:0.5rem; font-size:0.72rem; color:var(--text-muted); }
  .card-body { margin-top:0.7rem; font-size:0.9rem; line-height:1.95; }
  .card-link { display:inline-block; margin-top:0.9rem; font-size:0.82rem; font-weight:600;
    color:var(--accent); text-decoration:none; }
  .card-link:hover { text-decoration:underline; }
  .card.top { border-left-width:4px; background:linear-gradient(180deg,rgba(14,116,144,0.04),transparent); }
  .card.top .card-title-ja { font-size:1.25rem; }
  .tier { max-width:760px; margin:2rem auto 0.5rem; font-size:0.7rem; font-weight:700;
    letter-spacing:0.14em; color:var(--text-muted); }
  .tier:first-of-type { margin-top:0; }
  .podcast { max-width:760px; margin:2.5rem auto 0; padding:1.3rem 1.5rem;
    background:linear-gradient(135deg,#0f172a,#1e293b); border-radius:8px; color:#e2e8f0; }
  .podcast h2 { font-size:0.95rem; font-weight:700; color:#fff; margin-bottom:0.3rem; }
  .podcast p { font-size:0.82rem; color:#cbd5e1; }
  .podcast a { display:inline-block; margin-top:0.9rem; margin-right:0.6rem; padding:0.5rem 1.1rem;
    background:#22d3ee; color:#0f172a; font-size:0.8rem; font-weight:700;
    border-radius:6px; text-decoration:none; }
  .podcast a.ghost { background:none; border:1px solid rgba(255,255,255,0.35); color:#e2e8f0; }
  @media (max-width:640px){ .card{padding:1.15rem 1.2rem} .card.top .card-title-ja{font-size:1.1rem} }
"""


def _flatten(categorized: Dict[str, List[Dict]]) -> List[Dict]:
    """重要度の高い順に並べ替える。同順位はカテゴリの定義順で安定させる。"""
    items = []
    for category in CATEGORIES:
        for a in categorized.get(category, []):
            items.append({**a, "category": a.get("category", category)})
    items.sort(key=lambda a: (-int(a.get("importance", 2)), CATEGORIES.index(a["category"])))
    return items


def _card(article: Dict, emphasize: bool) -> str:
    category = article.get("category", "research")
    importance = max(1, min(3, int(article.get("importance", 2))))
    stars = "".join(
        f'<div class="dot{" filled" if i < importance else ""}"></div>' for i in range(3)
    )
    title_en = article.get("title_en", "")
    title_en_html = (f'      <div class="card-title-en">{_html.escape(title_en)}</div>\n'
                     if title_en else "")
    url = article.get("url", "")
    link_html = (f'      <a class="card-link" href="{_html.escape(url)}" target="_blank" '
                 f'rel="noopener">元記事を読む →</a>\n' if url else "")
    source = article.get("source", "")
    date = article.get("date", "")
    source_line = " · ".join(x for x in (source, date) if x)

    return (
        f'    <article class="card {category}{" top" if emphasize else ""}">\n'
        '      <div class="card-top">\n'
        f'        <span class="card-label {category}">{CATEGORIES_JA.get(category, category)}</span>\n'
        f'        <div class="stars">{stars}</div>\n'
        '      </div>\n'
        f'      <div class="card-title-ja">{_html.escape(article.get("title_ja", ""))}</div>\n'
        f'{title_en_html}'
        f'      <div class="card-source">{_html.escape(source_line)}</div>\n'
        f'      <div class="card-body">{_html.escape(article.get("summary", ""))}</div>\n'
        f'{link_html}'
        '    </article>\n'
    )


def _lead(overview: List[str]) -> str:
    if not overview:
        return ""
    items = "".join(f"      <li>{_html.escape(line)}</li>\n" for line in overview)
    return (
        '  <div class="lead">\n'
        '    <div class="lead-label">今日の3行まとめ</div>\n'
        f'    <ol>\n{items}    </ol>\n'
        "  </div>\n"
    )


def _podcast(date: datetime, available: bool) -> str:
    if not available:
        return ""
    base = monetize.podcast_url()
    date_iso = date.strftime("%Y-%m-%d")
    return (
        '  <div class="podcast">\n'
        "    <h2>🎧 音声で聴く</h2>\n"
        "    <p>今日のニュースを対話形式でまとめた音声版があります。通勤中や作業中にどうぞ。</p>\n"
        f'    <a href="{base}/podcast/player.html?date={date_iso}">再生する</a>\n'
        f'    <a class="ghost" href="{base}/podcast/feed.xml">RSSで購読</a>\n'
        "  </div>\n"
    )


def render(categorized: Dict[str, List[Dict]], date: datetime,
           overview: Optional[List[str]] = None,
           podcast_available: bool = False,
           config: Optional[Dict] = None) -> str:
    config = config if config is not None else monetize.load_config()
    site = config.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    name = site.get("name", "AI News Digest")

    items = _flatten(categorized)
    total = len(items)
    date_str = f"{date.year}年{date.month}月{date.day}日"
    date_iso = date.strftime("%Y-%m-%d")
    weekday = WEEKDAYS_JA[date.weekday()]

    head = monetize.build_head_tags(
        config,
        page_url=f"{base}/ai-news-{date_iso}.html" if base else "",
        title=f"AI最新ニュースまとめ {date_str} | {name}",
        description=(overview[0] if overview else
                     f"{date_str}のAI関連ニュース{total}件を日本語で要約してお届けします。"),
        published=f"{date_iso}T06:00:00+09:00",
    )

    # 重要度3を「注目」として先に出し、残りをその他としてまとめる
    top = [a for a in items if int(a.get("importance", 2)) >= 3]
    rest = [a for a in items if int(a.get("importance", 2)) < 3]

    body_parts = []
    if top:
        body_parts.append('  <div class="tier">注目のニュース</div>\n  <div class="digest">\n')
        body_parts += [_card(a, emphasize=True) for a in top]
        body_parts.append("  </div>\n")
    if rest:
        # 注目が1件も無い日に「そのほか」だけが出ると据わりが悪いので見出しを変える
        label = "そのほかの動き" if top else "本日のニュース"
        body_parts.append(f'  <div class="tier">{label}</div>\n  <div class="digest">\n')
        body_parts += [_card(a, emphasize=False) for a in rest]
        body_parts.append("  </div>\n")

    body = f"""<div class="hero">
  <div class="hero-inner">
    <div class="crumbs"><a href="./">{_html.escape(name)}</a> ／ <a href="archive.html">バックナンバー</a></div>
    <h1>{date_str}（{weekday}）のAIニュース</h1>
    <p>厳選 {total} 件。3分で今日のAIがわかります。</p>
  </div>
</div>

<main>
{_lead(overview or [])}
{"".join(body_parts)}
{_podcast(date, podcast_available)}
</main>

<footer>
  <strong>{_html.escape(name)}</strong> — {date_str}（{weekday}）／ {total} 件収録<br>
  毎朝6時に自動生成しています。
  {site_theme.footer_links(config)}
</footer>"""

    return site_theme.page_shell(
        f"AI最新ニュースまとめ {date_str} | {name}", head, body, extra_css=DIGEST_CSS
    )


if __name__ == "__main__":
    import social_kit
    c = social_kit.load_from_html("2026-07-16")
    html = render(c, datetime(2026, 7, 16),
                  overview=["サンプルの3行まとめです。", "2行目です。", "3行目です。"],
                  podcast_available=True)
    from pathlib import Path
    out = Path(".preview"); out.mkdir(exist_ok=True)
    (out / "digest-sample.html").write_text(html, encoding="utf-8")
    print(f"👀 .preview/digest-sample.html ({len(html):,} bytes)")
