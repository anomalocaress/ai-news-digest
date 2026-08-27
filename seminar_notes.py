#!/usr/bin/env python3
"""
セミナー録画 → 文字起こし・議事録・タイムスタンプ付き要約 → そのまま AI に質問できる状態にする。

## なぜ作ったか

NotebookLM の YouTube ソースは「一般公開されていて、字幕があり、投稿から
72時間以上経っている動画」しか読み込めない。中身を自前で文字起こしする機能は無く、
YouTube が返す字幕データをそのまま取り込んでいるだけなので、

  - 限定公開（リンクを知っている人だけ）のセミナー録画
  - 字幕がまだ生成されていない、または字幕を切っている動画

は URL を貼っても弾かれる。社内セミナーの録画はほぼ全部これに当たる。

回避策は昔から決まっていて「文字起こしをテキストとして渡す」。
このスクリプトはその文字起こしを取ってくるところから、議事録・
タイムスタンプ付き要約・ネクストアクションを書くところまでをまとめてやる。

## 使い方

    # 録画から一式（文字起こし＋議事録）を作る
    python seminar_notes.py https://youtu.be/XXXXXXXXXXX --title "第3回 社内勉強会"
    python seminar_notes.py ./recording.m4a --title "Zoom録画（2026-08-27）"

    # 文字起こしが既にあるなら、それを渡すのが一番速い
    # （YouTubeの「文字起こしを表示」からコピーしたもの、Zoomの字幕ファイルなど）
    python seminar_notes.py ./transcript.txt --title "第3回 社内勉強会"

    # 限定公開でログインが要る場合はブラウザの Cookie を借りる
    python seminar_notes.py <URL> --cookies-from-browser chrome

    # できたものに質問する（NotebookLM の代わり）
    python seminar_notes.py --ask "MCP版とAPI版の違いは？"
    python seminar_notes.py --ask "料金の話はどこ？" --slug rakumubi-benkyokai

    # 作ったセミナーの一覧
    python seminar_notes.py --list

## 出力（seminars/<スラッグ>/ 以下）

    transcript.txt   タイムスタンプ付きの文字起こし。NotebookLM に
                     「テキストを貼り付け」で渡せばソースとして使える
    notes.md         議事録・タイムスタンプ付き要約・ネクストアクション・
                     参加者への配布メール文面
    meta.json        元URL・取得方法・長さなどの記録

セミナーの中身は社外に出せないことが多いので seminars/ は .gitignore 済み。

## 文字起こしの取り方（上から順に試す）

    1. YouTube の字幕を API で取得（限定公開でも字幕さえあれば通る・無料）
    2. yt-dlp で自動生成字幕を取得（1が塞がれたとき用）
    3. 音声をダウンロードして Gemini で文字起こし（字幕が無い動画・ローカル音声）

3 だけは API キー（GEMINI_API_KEY / 予備で OPENAI_API_KEY）が要る。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SEMINAR_DIR = Path(__file__).resolve().parent / "seminars"

# 日本語のセミナーを想定。無ければ英語、それも無ければ動画にある任意の字幕。
DEFAULT_LANGS = ["ja", "ja-JP", "ja-orig", "en", "en-US"]

CLI_MODEL = "opus"
API_MODEL = "claude-opus-5"
GEMINI_MODEL = "gemini-flash-latest"


# ---------------------------------------------------------------------------
# 小道具
# ---------------------------------------------------------------------------

def _video_id(url: str) -> Optional[str]:
    """YouTube の各種URL形式から動画IDを取り出す。"""
    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtube\.com/(?:embed|shorts|live|v)/([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # ID だけを直接渡された場合
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return None


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def _slugify(text: str) -> str:
    """タイトルをフォルダ名として使える形にする。

    日本語はそのまま残す（フォルダ名として問題ない）。記号・空白だけを整理し、
    何も残らなかった場合は呼び出し側が日付ベースの名前で補う。
    """
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:60].lower()


def _hhmmss(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _run(cmd: List[str], timeout: int = 1800) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"コマンドが見つかりません: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "タイムアウトしました"


# ---------------------------------------------------------------------------
# 1. YouTube の字幕を API で取る
# ---------------------------------------------------------------------------

def _from_transcript_api(vid: str, langs: List[str], verbose: bool) -> Optional[List[Dict]]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        if verbose:
            print("   youtube-transcript-api が未インストールなのでスキップします")
        return None

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(vid, languages=langs)
    except Exception as e:
        if verbose:
            print(f"   字幕APIでは取れませんでした: {type(e).__name__}")
        return None

    # ライブラリのバージョンによって戻り値の形が違うので両対応にする
    try:
        raw = fetched.to_raw_data()
    except AttributeError:
        raw = [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]

    segments = [
        {"start": float(r.get("start", 0)), "text": str(r.get("text", "")).strip()}
        for r in raw
        if str(r.get("text", "")).strip()
    ]
    return segments or None


# ---------------------------------------------------------------------------
# 2. yt-dlp で自動生成字幕を取る
# ---------------------------------------------------------------------------

def _ytdlp_base(cookies: Optional[str], cookies_from_browser: Optional[str]) -> Optional[List[str]]:
    exe = shutil.which("yt-dlp")
    if not exe:
        return None
    cmd = [exe, "--no-warnings", "--no-progress"]
    if cookies:
        cmd += ["--cookies", cookies]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    return cmd


def _parse_json3(path: Path) -> List[Dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        segments.append({"start": float(ev.get("tStartMs", 0)) / 1000.0, "text": text})
    return segments


def _parse_vtt(path: Path) -> List[Dict]:
    """VTT を読む。自動生成字幕は同じ行が転がり続けるので重複を落とす。"""
    time_re = re.compile(r"(\d+:\d{2}:\d{2}[.,]\d{3})\s+-->\s+")
    segments: List[Dict] = []
    start = None
    buf: List[str] = []

    def flush():
        nonlocal start, buf
        if start is None:
            buf = []
            return
        text = " ".join(buf).strip()
        text = re.sub(r"<[^>]+>", "", text)          # <c> や <00:00:01.000> を除去
        text = re.sub(r"\s{2,}", " ", text).strip()
        if text and (not segments or segments[-1]["text"] != text):
            segments.append({"start": start, "text": text})
        start, buf = None, []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = time_re.search(line)
        if m:
            flush()
            h, mi, rest = m.group(1).split(":")
            sec = float(rest.replace(",", "."))
            start = int(h) * 3600 + int(mi) * 60 + sec
        elif line.strip() and not line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            buf.append(line.strip())
    flush()

    # 自動生成字幕は前の行を含んだまま次の行が出るので、包含関係の重複を畳む
    deduped: List[Dict] = []
    for seg in segments:
        if deduped and seg["text"].startswith(deduped[-1]["text"]):
            deduped[-1] = seg
        else:
            deduped.append(seg)
    return deduped


def _from_ytdlp_subs(url: str, langs: List[str], cookies: Optional[str],
                     browser: Optional[str], verbose: bool) -> Optional[List[Dict]]:
    base = _ytdlp_base(cookies, browser)
    if not base:
        if verbose:
            print("   yt-dlp が未インストールなのでスキップします")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sub"
        for fmt, parser in (("json3", _parse_json3), ("vtt", _parse_vtt)):
            code, _, err = _run(base + [
                "--skip-download", "--write-subs", "--write-auto-subs",
                "--sub-langs", ",".join(langs) + ",-live_chat",
                "--sub-format", fmt,
                "-o", str(out), url,
            ], timeout=300)
            files = sorted(Path(tmp).glob(f"*.{fmt}"))
            if files:
                # 希望言語の順に優先して選ぶ
                pick = files[0]
                for lang in langs:
                    hit = [f for f in files if f".{lang}." in f.name]
                    if hit:
                        pick = hit[0]
                        break
                try:
                    segments = parser(pick)
                except Exception as e:
                    if verbose:
                        print(f"   字幕ファイルを読めませんでした（{fmt}）: {e}")
                    continue
                if segments:
                    return segments
            elif verbose and code != 0:
                print(f"   yt-dlp が字幕を取れませんでした（{fmt}）: {err.strip()[:200]}")
    return None


# ---------------------------------------------------------------------------
# 3. 音声を落として文字起こしする
# ---------------------------------------------------------------------------

def _download_audio(url: str, dest: Path, cookies: Optional[str],
                    browser: Optional[str], verbose: bool) -> Optional[Path]:
    base = _ytdlp_base(cookies, browser)
    if not base:
        print("   ⚠️  yt-dlp が必要です（pip install yt-dlp）")
        return None
    if verbose:
        print("   音声をダウンロードしています…")
    out = dest / "audio.%(ext)s"
    code, _, err = _run(base + ["-f", "bestaudio/best", "-o", str(out), url], timeout=3600)
    if code != 0:
        print(f"   ⚠️  音声のダウンロードに失敗しました: {err.strip()[:300]}")
        return None
    files = [p for p in dest.iterdir() if p.stem == "audio"]
    return files[0] if files else None


_TRANSCRIBE_PROMPT = """この音声はセミナー・勉強会の録画です。話されている内容を一字一句、日本語で文字起こししてください。

ルール:
- 1行につき「[h:mm:ss] 発言内容」の形式で出力する（先頭は0:00から）
- おおよそ15〜30秒ごとに1行に区切る
- 話者が変わったところは行を分ける。誰が話しているか分かる場合は「[0:12:34] 講師: …」のように名前や役割を添える
- 要約・省略はしない。言い直しやフィラー（えー、あの）は適度に整えてよいが、内容は落とさない
- 文字起こし以外の前置きや説明は一切出力しない
"""


def _transcribe_gemini(path: Path, verbose: bool) -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        if verbose:
            print("   google-genai が未インストールなのでスキップします")
        return None

    if verbose:
        print(f"   Gemini で文字起こし中…（{path.stat().st_size / 1_000_000:.0f} MB）")
    try:
        client = google_genai.Client(api_key=api_key)
        uploaded = client.files.upload(file=str(path))
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[uploaded, _TRANSCRIBE_PROMPT],
            config=genai_types.GenerateContentConfig(temperature=0.0, max_output_tokens=65536),
        )
        text = (response.text or "").strip()
    except Exception as e:
        print(f"   ⚠️  Gemini での文字起こしに失敗しました: {e}")
        return None
    return text or None


def _transcribe_openai(path: Path, verbose: bool) -> Optional[str]:
    """予備。Whisper API は1ファイル25MBまでなので長時間の録画には向かない。"""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    size_mb = path.stat().st_size / 1_000_000
    if size_mb > 24:
        print(f"   ⚠️  音声が {size_mb:.0f} MB あり Whisper API の上限（25MB）を超えます。"
              "GEMINI_API_KEY を設定するか、音声を分割してください")
        return None
    try:
        import requests
    except ImportError:
        return None

    if verbose:
        print("   OpenAI で文字起こし中…")
    try:
        with path.open("rb") as f:
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, f)},
                data={"model": "whisper-1", "response_format": "verbose_json",
                      "language": "ja"},
                timeout=1800,
            )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"   ⚠️  OpenAI での文字起こしに失敗しました: {e}")
        return None

    lines = [f"[{_hhmmss(s.get('start', 0))}] {str(s.get('text', '')).strip()}"
             for s in data.get("segments", []) if str(s.get("text", "")).strip()]
    return "\n".join(lines) if lines else (data.get("text") or None)


def _from_audio(source: str, cookies: Optional[str], browser: Optional[str],
                verbose: bool) -> Optional[str]:
    """URL でも手元のファイルでも、音声から文字起こし済みテキストを返す。"""
    if not _is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            print(f"   ⚠️  ファイルが見つかりません: {path}")
            return None
        if path.suffix.lower() in TEXT_SUFFIXES:
            # テキストは既に fetch_transcript で扱っている。ここに来たなら中身が空。
            print(f"   ⚠️  文字起こしファイルが空か、読み取れませんでした: {path}")
            return None
        return _transcribe_gemini(path, verbose) or _transcribe_openai(path, verbose)

    with tempfile.TemporaryDirectory() as tmp:
        path = _download_audio(source, Path(tmp), cookies, browser, verbose)
        if not path:
            return None
        return _transcribe_gemini(path, verbose) or _transcribe_openai(path, verbose)


# ---------------------------------------------------------------------------
# 文字起こしの取得（全体）
# ---------------------------------------------------------------------------

TEXT_SUFFIXES = {".txt", ".md", ".vtt", ".srt", ".json3", ".json"}


def _from_text_file(path: Path, verbose: bool) -> Optional[str]:
    """すでに手元にある文字起こしを読み込む。

    YouTube の「文字起こしを表示」からコピーしたテキスト、Zoom や Teams が
    書き出した字幕ファイルなど、文字起こしが既にある場合はそれが一番速い。
    録画を取りに行けない環境でも、これなら議事録まで進められる。
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".vtt":
            return _format_segments(_parse_vtt(path))
        if suffix in (".json3", ".json"):
            return _format_segments(_parse_json3(path))
        if suffix == ".srt":
            return _format_segments(_parse_srt(path))
        return path.read_text(encoding="utf-8").strip() or None
    except Exception as e:
        if verbose:
            print(f"   ⚠️  文字起こしファイルを読めませんでした: {e}")
        return None


def _parse_srt(path: Path) -> List[Dict]:
    time_re = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s+-->")
    segments: List[Dict] = []
    start: Optional[float] = None
    buf: List[str] = []

    def flush():
        nonlocal start, buf
        text = " ".join(buf).strip()
        if start is not None and text:
            segments.append({"start": start, "text": text})
        start, buf = None, []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = time_re.search(line)
        if m:
            flush()
            h, mi, sec, ms = (int(g) for g in m.groups())
            start = h * 3600 + mi * 60 + sec + ms / 1000.0
        elif line.strip() and not line.strip().isdigit():
            buf.append(line.strip())
    flush()
    return segments


def fetch_transcript(source: str, langs: List[str], cookies: Optional[str],
                     browser: Optional[str], force_audio: bool,
                     verbose: bool = True) -> Optional[Tuple[str, str]]:
    """(文字起こしテキスト, 取得方法) を返す。取れなければ None。"""
    if not _is_url(source):
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() in TEXT_SUFFIXES and path.exists():
            if verbose:
                print("① 手元の文字起こしを読み込みます…")
            text = _from_text_file(path, verbose)
            if text:
                return text, "手元の文字起こしファイル"

    if _is_url(source) and not force_audio:
        vid = _video_id(source)
        if vid:
            if verbose:
                print("① YouTube の字幕を取得します…")
            segments = _from_transcript_api(vid, langs, verbose)
            if segments:
                return _format_segments(segments), "YouTubeの字幕（字幕API）"

            if verbose:
                print("② yt-dlp で自動生成字幕を取得します…")
            segments = _from_ytdlp_subs(source, langs, cookies, browser, verbose)
            if segments:
                return _format_segments(segments), "YouTubeの自動生成字幕（yt-dlp）"

    if verbose:
        print("③ 音声から文字起こしします…")
    text = _from_audio(source, cookies, browser, verbose)
    if text:
        return text, "音声からの文字起こし"
    return None


def _format_segments(segments: List[Dict]) -> str:
    """バラバラの字幕を、読める粒度（およそ30秒）にまとめる。"""
    lines: List[str] = []
    chunk_start: Optional[float] = None
    buf: List[str] = []

    for seg in segments:
        if chunk_start is None:
            chunk_start = seg["start"]
        buf.append(seg["text"].replace("\n", " ").strip())
        if seg["start"] - chunk_start >= 30:
            lines.append(f"[{_hhmmss(chunk_start)}] {' '.join(buf)}")
            chunk_start, buf = None, []
    if buf and chunk_start is not None:
        lines.append(f"[{_hhmmss(chunk_start)}] {' '.join(buf)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude を呼ぶ（サブスク枠の CLI を優先し、API を予備にする）
# ---------------------------------------------------------------------------

def ask_claude(system: str, user: str, max_tokens: int = 16000,
               purpose: str = "セミナー議事録", verbose: bool = True) -> Optional[str]:
    text = _claude_via_cli(system, user, verbose)
    if text:
        return text
    return _claude_via_api(system, user, max_tokens, purpose, verbose)


def _claude_via_cli(system: str, user: str, verbose: bool) -> Optional[str]:
    exe = shutil.which("claude")
    if not exe:
        return None

    # Claude Code は ANTHROPIC_API_KEY を OAuth トークンより優先してしまう。
    # 失効した API キーが環境に残っていると 401 で落ちるので外して渡す。
    env = os.environ.copy()
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        for k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)

    try:
        proc = subprocess.run(
            [exe, "-p", "--output-format", "json", "--model", CLI_MODEL],
            input=system + "\n\n---\n\n" + user,
            capture_output=True, text=True, timeout=1800, env=env,
        )
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Claude Code CLI の実行に失敗しました: {e}")
        return None

    if proc.returncode != 0:
        if verbose:
            print(f"   ⚠️  Claude Code CLI がエラーを返しました（exit {proc.returncode}）")
        return None

    try:
        wrapper = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout.strip() or None
    if wrapper.get("is_error"):
        if verbose:
            print(f"   ⚠️  Claude Code CLI が失敗を報告しました: {str(wrapper.get('result'))[:200]}")
        return None
    return str(wrapper.get("result", "")).strip() or None


def _claude_via_api(system: str, user: str, max_tokens: int, purpose: str,
                    verbose: bool) -> Optional[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        if verbose:
            print("   ⚠️  Claude Code CLI も ANTHROPIC_API_KEY も使えません")
        return None
    try:
        import anthropic
    except ImportError:
        if verbose:
            print("   ⚠️  anthropic パッケージが見つかりません（pip install anthropic）")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=API_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = next(b.text for b in response.content if b.type == "text")
    except Exception as e:
        print(f"   ⚠️  Claude API の呼び出しに失敗しました: {e}")
        return None

    try:
        import api_cost_calculator
        api_cost_calculator.record_anthropic_usage(
            model=API_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            purpose=purpose,
        )
    except Exception:
        pass
    return text.strip()


# ---------------------------------------------------------------------------
# 議事録を書く
# ---------------------------------------------------------------------------

NOTES_SYSTEM = """あなたは日本のIT企業で議事録を担当する編集者です。
セミナー・勉強会の録画の文字起こしを渡されるので、参加者と欠席者の両方が読んで
すぐ動ける資料にまとめます。

## 守ること

- 文字起こしに出てこないことは書かない。推測で補わない。
  聞き取れていない箇所は「（聞き取り不能）」と書く。
- タイムスタンプは文字起こしの [h:mm:ss] をそのまま使う。作らない。
- 文体は敬体（です・ます）で統一する。
- 固有名詞（製品名・ツール名・会社名・人名）は正確に。自信が無い表記は
  「〜（表記要確認）」と添える。
- ネクストアクションは「誰が・何を・いつまでに」が分かる形で書く。
  録画の中で担当や期限が決まっていない場合は「担当未定」「期限未定」と正直に書く。

## 出力形式

Markdown で、下の見出し構成のとおりに出力する。前置き・あとがき・
「以下にまとめました」のような一言は書かない。見出しから始める。

## タイムスタンプ付き要約

「前半｜セットアップ」のように話の区切りで小見出し（###）を立て、その下に
「0:00　開始前」「1:56　あいさつ・参加確認」のように1行ずつ、そのまま並べる。
表にもコードブロック（```）にもしないこと。メールに貼って読むものなので、
飾りが付くとかえって読みにくい。項目名は10〜20文字程度の名詞句にする。
行数は文字起こしにあるタイムスタンプの数に合わせる。数を揃えるために
存在しない時刻を作らないこと。逆に、行数が少ないことへの言い訳も書かないこと。

## 議事録

話し合われた内容を項目立ててまとめる。決まったこと・出た質問と回答・
保留になったことが分かるように書く。

## ツールの使い方

**この回でツールやサービスの操作説明があった場合だけ、この見出しを作る。**
雑談や報告だけの回では、この見出しごと省略してよい（無いものを埋めない）。

あとから動画を見返さずに手を動かせる粒度で書く。読む人は録画を見ていない、
あるいは見たが手順を覚えていない人。具体的には:

- セットアップ・導入は番号付きの手順にする。各手順の末尾に、動画の該当箇所の
  タイムスタンプを `（8:25）` のように添える。詰まったらそこへ飛べるようにするため
- 画面のどこを押すか、どのメニューか、何を入力するかを、録画で言われたとおりに書く
- 設定値・ファイル名・コマンド・URL・プラン名・金額は、**言われたまま正確に**書き写す。
  丸めない、言い換えない。ここを要約すると資料として使えなくなる
- 「ここでよく間違える」「ここは飛ばしていい」といった注意が出てきたら、
  該当手順の下に「⚠️」付きで残す
- 複数のやり方（例: 版・プラン・モードの違い）が説明されたなら、
  表で並べて違いが一目で分かるようにする
- 質疑で出た「こうしたい時はどうするか」も、操作の話ならここにまとめる

## 決まったこと

箇条書き。無ければ「特にありません」と書く。

## ネクストアクション

- [ ] 担当：やること（期限）

の形の箇条書き。

## 参加者への配布メール文面

そのままコピーして送れる本文。冒頭に一言、続けて議事録URL・録画URL・
タイムスタンプ付き要約の順に並べる。URL は差し込み用に
「（議事録URLをここに）」のようなプレースホルダにする（録画URLが分かっている場合はそれを使う）。
"""


def build_notes(title: str, transcript: str, source: str, focus: str = "",
                verbose: bool = True) -> Optional[str]:
    if verbose:
        print("④ 議事録・要約を作成しています…")
    focus_block = (
        f"# この回で特に厚く書いてほしいところ\n{focus}\n\n"
        "上の指示は、決められた見出し構成の中で反映してください。"
        "見出しを増やしたり順番を変えたりはしないこと。\n\n"
    ) if focus.strip() else ""
    user = (
        f"# セミナー名\n{title}\n\n"
        f"# 録画URL\n{source if _is_url(source) else '（ローカル録画）'}\n\n"
        f"{focus_block}"
        f"# 文字起こし\n\n{transcript}"
    )
    return ask_claude(NOTES_SYSTEM, user, max_tokens=16000,
                      purpose="セミナー議事録の作成", verbose=verbose)


# ---------------------------------------------------------------------------
# 質問する
# ---------------------------------------------------------------------------

QA_SYSTEM = """あなたはセミナーの内容に詳しいアシスタントです。
渡された文字起こしだけを根拠に、日本語で質問に答えます。

- 文字起こしに書かれていないことは「録画の中では触れられていません」と答える。
  推測で埋めない。
- 答えの根拠になった箇所のタイムスタンプを必ず [h:mm:ss] の形で示す。
- 長くならないように。要点を先に書き、必要なら補足を続ける。
"""


def answer(slug: str, question: str, verbose: bool = True) -> Optional[str]:
    d = SEMINAR_DIR / slug
    transcript_path = d / "transcript.txt"
    if not transcript_path.exists():
        print(f"⚠️  文字起こしが見つかりません: {transcript_path}")
        return None
    meta = {}
    if (d / "meta.json").exists():
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))

    user = (
        f"# セミナー名\n{meta.get('title', slug)}\n\n"
        f"# 文字起こし\n\n{transcript_path.read_text(encoding='utf-8')}\n\n"
        f"# 質問\n{question}"
    )
    return ask_claude(QA_SYSTEM, user, max_tokens=4000,
                      purpose="セミナー内容への質問", verbose=verbose)


# ---------------------------------------------------------------------------
# 保存 / 一覧
# ---------------------------------------------------------------------------

def _resolve_slug(explicit: Optional[str], title: str) -> str:
    if explicit:
        return explicit
    slug = _slugify(title)
    stamp = datetime.now().strftime("%Y-%m-%d")
    return f"{stamp}-{slug}" if slug else f"seminar-{stamp}"


def latest_slug() -> Optional[str]:
    if not SEMINAR_DIR.exists():
        return None
    dirs = [d for d in SEMINAR_DIR.iterdir() if (d / "transcript.txt").exists()]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime).name


def list_seminars() -> None:
    if not SEMINAR_DIR.exists() or not any(SEMINAR_DIR.iterdir()):
        print("まだセミナーがありません。")
        print("  python seminar_notes.py <録画URL または音声ファイル> --title \"セミナー名\"")
        return
    print("保存済みのセミナー:\n")
    for d in sorted(SEMINAR_DIR.iterdir()):
        if not (d / "transcript.txt").exists():
            continue
        meta = {}
        if (d / "meta.json").exists():
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            except Exception:
                pass
        chars = len((d / "transcript.txt").read_text(encoding="utf-8"))
        notes = "議事録あり" if (d / "notes.md").exists() else "議事録なし"
        print(f"  {d.name}")
        print(f"    {meta.get('title', '(タイトル未設定)')} / {chars:,}字 / {notes}")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="セミナー録画から文字起こし・議事録を作り、内容に質問できるようにする",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 使い方")[1].split("## 出力")[0] if "## 使い方" in __doc__ else "",
    )
    parser.add_argument("source", nargs="?",
                        help="録画のURL（YouTube等）、音声・動画ファイル、"
                             "または文字起こし済みのテキスト（.txt/.vtt/.srt）")
    parser.add_argument("--title", default="", help="セミナー名（議事録の見出しに使う）")
    parser.add_argument("--slug", help="保存先フォルダ名。省略時は日付＋タイトルから作る")
    parser.add_argument("--lang", default="", help="字幕の言語を指定（例: ja）")
    parser.add_argument("--cookies", help="Cookie ファイル（限定公開・要ログインの動画用）")
    parser.add_argument("--cookies-from-browser", help="ブラウザから Cookie を借りる（chrome / firefox 等）")
    parser.add_argument("--audio", action="store_true", help="字幕を使わず音声から文字起こしする")
    parser.add_argument("--focus", default="",
                        help="議事録で厚く書いてほしいところ（例: \"ツールの使い方を手順まで詳しく\"）")
    parser.add_argument("--no-notes", action="store_true", help="文字起こしだけ作って議事録は作らない")
    parser.add_argument("--ask", metavar="質問", help="保存済みのセミナーに質問する")
    parser.add_argument("--list", action="store_true", help="保存済みのセミナー一覧")
    args = parser.parse_args()

    if args.list:
        list_seminars()
        return 0

    if args.ask:
        slug = args.slug or latest_slug()
        if not slug:
            print("⚠️  まだセミナーが登録されていません。先に録画を読み込んでください。")
            return 1
        print(f"📖 {slug} に質問します\n")
        result = answer(slug, args.ask)
        if not result:
            return 1
        print(result)
        return 0

    if not args.source:
        parser.print_help()
        return 1

    title = args.title or (args.source if not _is_url(args.source) else "セミナー録画")
    langs = [args.lang] + DEFAULT_LANGS if args.lang else DEFAULT_LANGS

    print(f"🎥 {title}")
    print(f"   ソース: {args.source}\n")

    got = fetch_transcript(args.source, langs, args.cookies,
                           args.cookies_from_browser, args.audio)
    if not got:
        print("\n⚠️  文字起こしを取得できませんでした。次のどれかを試してください:")
        print("   - 限定公開でログインが要る場合: --cookies-from-browser chrome")
        print("   - 字幕が無い動画: GEMINI_API_KEY を設定して --audio")
        print("   - 手元に録画ファイルがあるなら、URL の代わりにファイルを渡す")
        return 1

    transcript, method = got
    print(f"   ✅ 文字起こしを取得しました（{method} / {len(transcript):,}字）\n")

    slug = _resolve_slug(args.slug, title)
    outdir = SEMINAR_DIR / slug
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "transcript.txt").write_text(transcript, encoding="utf-8")
    (outdir / "meta.json").write_text(json.dumps({
        "title": title,
        "source": args.source,
        "method": method,
        "chars": len(transcript),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_notes:
        notes = build_notes(title, transcript, args.source, args.focus)
        if notes:
            (outdir / "notes.md").write_text(f"# {title}\n\n{notes}\n", encoding="utf-8")
            print("   ✅ 議事録を作成しました\n")
        else:
            print("   ⚠️  議事録の作成は失敗しましたが、文字起こしは保存済みです\n")

    print(f"📁 {outdir}")
    print(f"   transcript.txt … NotebookLM に「テキストを貼り付け」で渡せます")
    if (outdir / "notes.md").exists():
        print(f"   notes.md       … 議事録・タイムスタンプ付き要約・配布メール文面")
    print(f"\n💬 質問する:")
    print(f"   python seminar_notes.py --ask \"知りたいこと\" --slug {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
