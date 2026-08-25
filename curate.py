#!/usr/bin/env python3
"""
記事のキュレーション — 「捨てる・選ぶ・日本語で書く」を Claude に任せる。

これまでの実装の問題:
  - 選別が無く、取得した50件をそのまま全部載せていた
  - カテゴリ分けがキーワードマッチだったので誤爆していた
    （AIと無関係な記事が「研究」に入る等）
  - 日本語化が Google 翻訳の直訳だったため、固有名詞の誤訳や
    不自然な分かち書き、敬体と常体の混在が起きていた

ここでやること:
  1. AI に実質的に関係する記事だけを残す
  2. 重複を1本にまとめる
  3. 日本語の見出しとして自然なタイトルを「書く」（翻訳ではない）
  4. 「何が起きたか・なぜ重要か」を2〜3文で書く
  5. カテゴリと重要度を判定する

失敗しても止めない:
  API キーが無い・通信に失敗した等の場合は None を返し、
  呼び出し側は従来のキーワード分類＋機械翻訳にフォールバックする。
"""

import json
import os
from typing import Dict, List, Optional

import monetize

CATEGORIES = ["model", "research", "business", "policy", "tools"]

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MIN = 8
DEFAULT_MAX = 12

SYSTEM_PROMPT = """あなたは日本のAI専門メディアの編集者です。
その日に集まった英語のテック記事から、日本の読者に届ける価値のあるものだけを選び、日本語で書き直します。

## 選ぶ基準

- AI・機械学習に**実質的に**関係する記事だけを残す。
  単に「テック企業のニュース」というだけのもの、AIに触れていない製品・企業・訴訟の話は落とす。
- 同じ出来事を報じた記事が複数あれば、最も情報量の多い1本にまとめる。
- 残りは重要度の高い順に並べる。

## 日本語の書き方

- **翻訳しない。日本語の見出しとして書き直す。** 直訳調は禁止。
- 製品名・企業名・人名・ニュースレター名などの固有名詞は訳さずそのまま使う。
  （例: "The Download" はニュースレター名なので「ダウンロード」と訳さない）
- カタカナ語を不自然に分かち書きしない。
  （×「カスタマー サービス エクスペリエンス」→ ○「カスタマーサポート体験」）
- 文体は敬体（です・ます）で統一する。常体と混ぜない。
- 要約は2〜3文で、「何が起きたか」に加えて「なぜ重要か / 何が変わるか」を必ず書く。
  元記事の説明文をなぞるだけにしない。

## カテゴリ

- model: 新しいモデル・性能・リリース
- research: 研究成果・論文・技術的な発見
- business: 資金調達・買収・提携・市場動向・採用
- policy: 規制・訴訟・倫理・安全性・著作権
- tools: 開発者向けツール・API・製品機能

## 重要度

- 3: その日の主要ニュース。業界の流れが変わりうるもの
- 2: 知っておきたいが、決定的ではないもの
- 1: 参考程度

判断に迷ったら「載せない」を選んでください。件数を埋めるために質を落とさないこと。"""


CURATION_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "array",
            "description": "その日の要点を3行で。1行はそれぞれ40〜60字程度の日本語の文。",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "入力リストで示された記事の番号",
                    },
                    "title_ja": {"type": "string", "description": "日本語の見出し（40字以内）"},
                    "summary": {"type": "string", "description": "2〜3文の日本語要約"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["index", "title_ja", "summary", "category", "importance"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overview", "articles"],
    "additionalProperties": False,
}


def _config() -> Dict:
    return monetize.load_config().get("curation", {}) or {}


def _cli_available() -> bool:
    import shutil
    return shutil.which("claude") is not None


def is_enabled() -> bool:
    return bool(_config().get("enabled", True)) and (
        _cli_available()
        or bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))
    )


def _build_user_message(articles: List[Dict], min_n: int, max_n: int) -> str:
    lines = [
        f"本日集まった記事は {len(articles)} 件です。"
        f"この中から掲載する価値のあるものを {min_n}〜{max_n} 件選び、日本語で書き直してください。",
        "",
        "AIに関係する記事が少ない日は、無理に件数を埋めず少なくて構いません。",
        "",
        "---",
        "",
    ]
    for i, a in enumerate(articles):
        desc = (a.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 400:
            desc = desc[:400] + "…"
        lines.append(f"[{i}] {a.get('title', '')}")
        lines.append(f"    出典: {a.get('source', '不明')}")
        if desc:
            lines.append(f"    概要: {desc}")
        lines.append("")
    return "\n".join(lines)


def _extract_json(text: str) -> Optional[Dict]:
    """CLI の応答テキストから JSON オブジェクトを取り出す。

    コードフェンスや前置きが混ざることがあるため、最初の '{' から
    対応する '}' までをバランスを取りながら切り出す。
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _curate_via_cli(articles: List[Dict], cfg: Dict, min_n: int, max_n: int,
                    verbose: bool) -> Optional[Dict]:
    """Claude Code CLI（サブスクリプション枠）でキュレーションする。

    Max プラン契約者は `claude setup-token` で発行した OAuth トークンを
    CLAUDE_CODE_OAUTH_TOKEN として渡せば、API の従量課金なしで動く。
    ローカルではログイン済みの CLI がそのまま使われる。
    """
    import shutil
    import subprocess

    exe = shutil.which("claude")
    if not exe:
        return None

    schema_str = json.dumps(CURATION_SCHEMA, ensure_ascii=False)
    prompt = (
        SYSTEM_PROMPT
        + "\n\n## 出力形式\n\n"
        + "次の JSON Schema に**厳密に**従う JSON オブジェクトだけを出力してください。"
        + "前置き・説明・コードフェンスは一切付けないこと。\n\n"
        + schema_str
        + "\n\n---\n\n"
        + _build_user_message(articles, min_n, max_n)
    )

    cmd = [exe, "-p", "--output-format", "json",
           "--model", cfg.get("cli_model", "opus")]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        if verbose:
            print("   ⚠️  Claude Code CLI がタイムアウトしました")
        return None
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Claude Code CLI の実行に失敗しました: {e}")
        return None

    if proc.returncode != 0:
        if verbose:
            err = (proc.stderr or proc.stdout or "").strip()[:200]
            print(f"   ⚠️  Claude Code CLI がエラーを返しました: {err}")
        return None

    try:
        wrapper = json.loads(proc.stdout)
    except json.JSONDecodeError:
        wrapper = {"result": proc.stdout}

    if wrapper.get("is_error"):
        if verbose:
            print(f"   ⚠️  Claude Code CLI が失敗を報告しました: {str(wrapper.get('result'))[:200]}")
        return None

    data = _extract_json(wrapper.get("result", ""))
    if data is None:
        if verbose:
            print("   ⚠️  CLI の応答から JSON を取り出せませんでした")
        return None

    if verbose:
        usage = wrapper.get("usage") or {}
        if usage:
            print(f"   使用トークン: 入力 {usage.get('input_tokens', 0):,} / "
                  f"出力 {usage.get('output_tokens', 0):,}（サブスクリプション枠）")

    return data


def curate(articles: List[Dict], verbose: bool = True) -> Optional[Dict]:
    """記事を選別して日本語化する。

    Returns:
        {"overview": [3行], "categorized": {category: [記事…]}} 形式。
        利用できない場合は None（呼び出し側は従来処理にフォールバックする）。
    """
    if not articles:
        return None

    cfg = _config()
    if not cfg.get("enabled", True):
        if verbose:
            print("   キュレーションは設定で無効化されています")
        return None

    min_n = int(cfg.get("min_articles", DEFAULT_MIN))
    max_n = int(cfg.get("max_articles", DEFAULT_MAX))
    backend = cfg.get("backend", "auto")

    # サブスクリプション枠（Claude Code CLI）を優先し、API を予備にする。
    # backend: "claude-code" = CLI のみ / "api" = API のみ / "auto" = CLI → API の順
    if backend in ("auto", "claude-code"):
        data = _curate_via_cli(articles, cfg, min_n, max_n, verbose)
        if data is not None:
            result = _assemble(data, articles, verbose)
            if result is not None:
                return result
        if backend == "claude-code":
            if verbose:
                print("   ⚠️  CLI バックエンドが使えませんでした（従来処理で続行）")
            return None
        if verbose:
            print("   CLI が使えないため API にフォールバックします")

    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        if verbose:
            print("   ⚠️  ANTHROPIC_API_KEY も未設定のためキュレーションをスキップします")
        return None

    model = cfg.get("model", DEFAULT_MODEL)

    try:
        import anthropic
    except ImportError:
        if verbose:
            print("   ⚠️  anthropic パッケージが見つかりません（pip install anthropic）")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(articles, min_n, max_n)}],
            output_config={
                "effort": cfg.get("effort", "medium"),
                "format": {"type": "json_schema", "schema": CURATION_SCHEMA},
            },
        )
    except Exception as e:
        if verbose:
            print(f"   ⚠️  キュレーションに失敗しました（従来処理で続行）: {e}")
        return None

    if getattr(response, "stop_reason", None) == "refusal":
        if verbose:
            print("   ⚠️  モデルが応答を拒否しました（従来処理で続行）")
        return None

    try:
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
    except Exception as e:
        if verbose:
            print(f"   ⚠️  応答を解釈できませんでした（従来処理で続行）: {e}")
        return None

    _record_usage(response, model, verbose)
    return _assemble(data, articles, verbose)


def _record_usage(response, model: str, verbose: bool):
    """API 使用量を記録して、コストダッシュボードに反映させる。"""
    try:
        import api_cost_calculator
        api_cost_calculator.record_anthropic_usage(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            purpose="ニュースの選別・日本語化",
        )
        if verbose:
            print(f"   使用トークン: 入力 {response.usage.input_tokens:,} / "
                  f"出力 {response.usage.output_tokens:,}")
    except Exception:
        pass


def _assemble(data: Dict, articles: List[Dict], verbose: bool) -> Optional[Dict]:
    """モデルの出力を元記事とつき合わせて、既存の categorized 形式に組み立てる。"""
    picked = data.get("articles", [])
    if not picked:
        if verbose:
            print("   ⚠️  掲載対象が0件でした（従来処理で続行）")
        return None

    categorized: Dict[str, List[Dict]] = {c: [] for c in CATEGORIES}
    seen = set()

    for item in picked:
        idx = item.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(articles)) or idx in seen:
            continue  # モデルが存在しない番号を返した場合に備える
        seen.add(idx)

        src = articles[idx]
        category = item.get("category") if item.get("category") in CATEGORIES else "research"
        categorized[category].append({
            "title_en": src.get("title", ""),
            "title_ja": item.get("title_ja", "").strip(),
            "summary": item.get("summary", "").strip(),
            "category": category,
            "importance": max(1, min(3, int(item.get("importance", 2)))),
            "source": src.get("source", ""),
            "url": src.get("url", ""),
            "date": src.get("date", ""),
        })

    total = sum(len(v) for v in categorized.values())
    if total == 0:
        return None

    overview = [s.strip() for s in data.get("overview", []) if s and s.strip()]
    if verbose:
        print(f"   ✓ {len(articles)} 件 → {total} 件に選別しました")
        for c in CATEGORIES:
            if categorized[c]:
                print(f"      {c}: {len(categorized[c])} 件")

    return {"overview": overview, "categorized": categorized}


if __name__ == "__main__":
    # 実データで動作確認する（要 ANTHROPIC_API_KEY）
    import sys
    from datetime import datetime
    import generate_news

    target = datetime.now()
    if len(sys.argv) > 2 and sys.argv[1] == "--date":
        target = datetime.strptime(sys.argv[2], "%Y-%m-%d")

    raw = generate_news.fetch_rss_news(target)
    print(f"取得: {len(raw)} 件")
    result = curate(raw)
    if result:
        print("\n--- 今日の3行まとめ ---")
        for line in result["overview"]:
            print(f"  ・{line}")
        print("\n--- 掲載記事 ---")
        for cat, items in result["categorized"].items():
            for a in items:
                print(f"  [{cat}] {'★' * a['importance']} {a['title_ja']}")
                print(f"        {a['summary']}")
