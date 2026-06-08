#!/usr/bin/env python3
"""
てらこAIニュースダイジェスト — 2人対話型ポッドキャスト生成
Gemini 1.5 Flash（無料枠）で台本生成 + edge-tts（KeitaNeural/NanamiNeural）+ pydub で音声合成。
GEMINI_API_KEY が未設定のときはシンプルなフォールバック台本を使用。
"""

import asyncio
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from generate_podcast import (
    PODCAST_DIR, BASE_URL, PODCAST_EMAIL, COVER_URL,
    CATEGORIES_JA, WEEKDAYS_JA, MAX_PER_CATEGORY,
    clean_text, preprocess_for_tts, select_top_articles, update_feed,
)

# ---------------------------------------------------------------------------
# キャスト設定
# ---------------------------------------------------------------------------
VOICE_TERAKO = "ja-JP-KeitaNeural"   # てらこ先生（男性）
VOICE_MIKA   = "ja-JP-NanamiNeural"  # ミカ（女性）

# edge-tts の音声パラメータ（rate / pitch）
# rate は自然な等速（+0%）。速度はプレイヤー側で各自調整する方針。
# 初めて聴く人が速すぎないよう、音声自体は自然なテンポで生成する。
# pitch でキャラクターのイントネーションに変化をつける。
VOICE_PARAMS = {
    "てらこ先生": {
        "voice": VOICE_TERAKO,
        "rate":  "+0%",
        "pitch": "-2Hz",   # 落ち着いた声色を維持
    },
    "ミカ": {
        "voice": VOICE_MIKA,
        "rate":  "+0%",
        "pitch": "+5Hz",   # やや明るく、抑揚を強める
    },
}

# セグメント間の無音（ミリ秒）
SILENCE_SAME_SPEAKER    = 220   # 同一話者の連続発話間
SILENCE_SPEAKER_CHANGE  = 420   # 話者切り替え時


# ---------------------------------------------------------------------------
# Gemini 用システムプロンプト
# （PDFのニュースレター3原則 + 対話フォーマット）
# ---------------------------------------------------------------------------
_DIALOGUE_SYSTEM_PROMPT = """\
あなたは、AIに造詣が深い専門家やビジネスパーソン向けの高品質なAIトレンドポッドキャスト台本を作成するAIエージェントです。
入力された複数ジャンルのニュース情報を整理し、聴取者の認知負担を下げつつ説得力を最大化するために、以下のルールに従って台本を生成してください。

【キャスト】
- てらこ先生（男性ホスト）：専門家らしい知識を持ちながらも、親しみやすく明るいトーンで話します。自分自身のことは「私」ではなく必ず「てらこ先生」と三人称で呼んでください（例：「てらこ先生が注目しているのは〜」「それはてらこ先生も驚きました」）。番組名「てらこAIニュースダイジェスト」のアカウント名でもあります。
- ミカ（女性アナウンサー）：明るく元気な口調で、リアクション・深掘り質問・感想を担当します。

【台本フォーマット（厳守）】
以下の形式のみを使用してください。それ以外の形式（#見出し、箇条書きなど）は一切使わないでください。
[てらこ先生] テキスト
[ミカ] テキスト
[てらこ先生] テキスト
...

【ニュースレター構成3原則（ポッドキャスト版）】

1. 意味のあるカテゴリーへのグループ化（ナラティブの構築）
入力ニュースを単なる時系列や主観的な重要度順に並べないでください。
「AIエージェントの自律化と開発環境の進化」「一般向けAIアプリの最新動向」「社会実装と規制の最前線」など、
現在のトレンドを象徴する意味のあるカテゴリーで再編成してください。
業界全体が異常なスピードで動いているという大きな物語（構造的なカオス）として聴かせてください。

2. 誇張表現の排除と事実・データによるトーンの徹底
「革命的」「歴史的転換点」「画期的」「劇的に向上」「魔法のような」といった主観的な誇張表現・マーケティング用語は一切使わないでください。
「従来比で推論精度が40パーセント向上」「膵臓がんを最大3年早く発見」のような客観的な数値・データで事実に語らせてください。

3. 考察と証拠の直下インサート
専門家の見解・重要データは番組末尾にまとめて紹介するのではなく、該当ニュースの直後の自然な会話の流れで挿入してください。
核心となる1〜2文だけを抽出して言及し、詳細は「詳しくは記事をご覧ください」と流す構成にしてください。

【ニュースの取捨選択（最重要）】
- 入力には複数の情報源（ニュースメディア、X（旧Twitter）の投稿、Hacker News の話題）が含まれます。
- その中から「本当に重要なもの」かつ「一般のユーザーが関心を持つもの」だけを厳選してください。
- 取り上げる本数の目安は5〜7件。多すぎると一件あたりが薄くなり、尺も超過します。
- 次のようなものは優先的に取り上げる：
  - 多くの人の生活や仕事に影響する発表（主要モデルの公開、身近なサービスの新機能など）
  - 具体的な数値・成果が伴う研究（医療、安全性など社会的インパクトの大きいもの）
  - 大きな資金の動き、規制・政策の変化
  - X や Hacker News で話題になっている（注目度が高い）トピック
- 次のようなものは省略する：
  - 専門家しか関心を持たない極端にニッチ・技術的な話題
  - 宣伝色が強いだけの製品告知、内容の薄い小ネタ
- X 由来の情報は「〇〇社が公式Xで発表したところによると」のように出典に触れてください。

【ポッドキャスト構成】
1. オープニング：てらこ先生が番組名・日付・今日のハイライトを紹介し、ミカと軽く掛け合う（約2〜3ターン）
2. ニュース本編：厳選した話題を「てらこ先生が解説→ミカが質問またはコメント→てらこ先生が深掘り」で進める
3. クロージング：てらこ先生とミカがまとめを行い、次回予告で締める（約2ターン）

【トーン・スタイル】
- 専門的な内容も、明るくテンポよく届けてください。「堅い講義」ではなく「楽しいラジオ番組」のイメージで。
- てらこ先生は知的でありながら気さくで、ときどき軽いユーモアを交えてもOKです。
- ミカは元気よく反応し、リスナーの代わりに「えっ、それってどういうことですか？」と素直に聞いてください。

【尺・品質（厳守）】
- 必ず10分以内に収めてください。文字数の目安は2800〜3300文字（これを超えないこと）。
- そのために本数を絞り、一件一件を分かりやすく深掘りしてください（広く浅くにしない）。
- 数字は日本語読みで記載してください（例：100→百、3%→3パーセント、GPT-5→ジーピーティーファイブ）
- てらこ先生はオープニングで「てらこAIニュースダイジェスト」と番組名を必ず読み上げてください
- てらこ先生が自分を指すときは必ず「てらこ先生」と言ってください（「私は〜」は使わない）
- 台本は必ずクロージングまで書き切り、途中で終わらせないこと。
"""


# ---------------------------------------------------------------------------
# Gemini による対話台本生成
# ---------------------------------------------------------------------------

def build_dialogue_script(articles_by_category: Dict[str, List[Dict]], date: datetime) -> str:
    """Gemini 2.0 Flash で2人対話形式の台本を生成する。失敗時はフォールバック。"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("  ⚠️  GEMINI_API_KEY 未設定。フォールバック台本を使用。")
        return _fallback_script(articles_by_category, date)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        print("  ⚠️  google-genai 未インストール。pip install google-genai")
        return _fallback_script(articles_by_category, date)

    client = google_genai.Client(api_key=api_key)

    date_str = date.strftime("%Y年%m月%d日")
    weekday  = WEEKDAYS_JA[date.weekday()]
    selected = select_top_articles(articles_by_category)

    # ---- 記事データを整形してプロンプトに渡す ----
    news_text = f"【{date_str}（{weekday}曜日）のAIニュース一覧】\n\n"
    for category, cat_name in CATEGORIES_JA.items():
        articles = selected.get(category, [])
        if not articles:
            continue
        news_text += f"■ {cat_name}\n"
        for art in articles:
            title   = clean_text(art.get("title_ja") or art.get("title_en") or "")
            summary = clean_text(art.get("summary") or "")
            source  = art.get("source", "")
            if summary in ("Read the full article for details.", "詳細は記事をご覧ください。"):
                summary = ""
            line = f"・{title}"
            if source:
                line += f"（{source}）"
            if summary:
                line += f"\n  概要: {summary[:300]}"
            news_text += line + "\n"
        news_text += "\n"

    user_prompt = (
        f"{news_text}\n"
        f"上記のニュースを元に、{date_str}版の「てらこAIニュースダイジェスト」台本を生成してください。"
    )

    # 最大3回まで再試行（空レスポンス・一時的エラーへの対策）
    for attempt in range(1, 4):
        print(f"  Gemini Flash で台本生成中... (試行 {attempt}/3)")
        try:
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_DIALOGUE_SYSTEM_PROMPT,
                    temperature=0.7,
                    # 台本が途中で切れないよう上限を引き上げる
                    # （gemini-flash-latest は 8192 まで対応）
                    max_output_tokens=8192,
                ),
            )

            # finish_reason を取得（MAX_TOKENS = トークン上限で切れた）
            finish_reason = None
            try:
                if response.candidates:
                    finish_reason = str(response.candidates[0].finish_reason or "")
            except Exception:
                pass

            # response.text が None や空のことがある（safety filter / token 制限など）
            raw_text = response.text or ""
            script = raw_text.strip()

            # 空 or [てらこ先生]/[ミカ] タグを含まない場合は無効と判定
            if not script:
                print(f"  ⚠️  Gemini が空レスポンスを返却（finish_reason={finish_reason}）")
                try:
                    for cand in (response.candidates or []):
                        if cand.safety_ratings:
                            for sr in cand.safety_ratings:
                                print(f"     safety: {sr.category} = {sr.probability}")
                except Exception:
                    pass
                continue
            if "[てらこ先生]" not in script and "[ミカ]" not in script:
                print(f"  ⚠️  対話タグが見つかりません（{len(script)} 文字） → リトライ")
                continue

            # トークン上限で台本が途中で切れた場合の救済
            if finish_reason and "MAX_TOKENS" in finish_reason.upper():
                print(f"  ⚠️  台本がトークン上限で途中終了（{len(script)} 文字）→ 末尾を整える")
                script = _repair_truncated_script(script, date)
            else:
                print(f"  ✓ 台本生成完了: {len(script)} 文字")
            return script

        except Exception as e:
            print(f"  ⚠️  Gemini API エラー (試行 {attempt}): {e}")
            if attempt < 3:
                import time
                time.sleep(5)  # 5秒待ってリトライ

    print("  ⚠️  Gemini で台本生成に失敗 → ルールベースのフォールバック台本を使用します")
    return _fallback_script(articles_by_category, date)


def _repair_truncated_script(script: str, date: datetime) -> str:
    """
    トークン上限で途中終了した台本の末尾を整える。
    - 不完全な最終行（タグだけ／極端に短い発話）を削除
    - 自然なクロージングを追加
    """
    date_str = date.strftime("%Y年%m月%d日")
    lines = script.splitlines()

    # 末尾から、内容のある対話行まで遡る
    cleaned: List[str] = []
    for line in lines:
        cleaned.append(line)

    # 末尾の不完全な行を除去（タグのみ、または15文字未満の中身しかない発話）
    while cleaned:
        last = cleaned[-1].strip()
        if not last:
            cleaned.pop()
            continue
        m = re.match(r"^\[(てらこ先生|ミカ)\]\s*(.*)$", last)
        if m:
            body = m.group(2).strip()
            # 「はい。」のような相槌だけ、または文が途中で切れている場合は削除
            if len(body) < 15 or not re.search(r"[。！？」）]$", body):
                cleaned.pop()
                continue
        break

    # クロージングを追加（最後の話者と重複しないようにミカ→てらこ先生で締める）
    cleaned.append("")
    cleaned.append(
        "[ミカ] さて、今日もあっという間でしたね。盛りだくさんの内容をお届けしました。"
    )
    cleaned.append(
        f"[てらこ先生] そうですね。以上、{date_str}版の「てらこAIニュースダイジェスト」でした。"
        "それでは、また次回お会いしましょう。"
    )
    cleaned.append("[ミカ] ありがとうございました。")

    repaired = "\n".join(cleaned)
    print(f"  ✓ 台本を補修してクロージングを追加: {len(repaired)} 文字")
    return repaired


def _fallback_script(articles_by_category: Dict[str, List[Dict]], date: datetime) -> str:
    """Gemini が使えない場合のルールベース対話台本。"""
    date_str = date.strftime("%Y年%m月%d日")
    weekday  = WEEKDAYS_JA[date.weekday()]
    selected = select_top_articles(articles_by_category)
    total    = sum(len(v) for v in selected.values())

    lines: List[str] = []
    lines.append(
        f"[てらこ先生] おはようございます！てらこAIニュースダイジェスト、"
        f"{date_str}{weekday}曜日版です！てらこ先生が本日の注目{total}件をお届けします。"
        f"ミカさん、今日もよろしく！"
    )
    lines.append("[ミカ] よろしくお願いします！今日はどんなニュースが来ているか、ワクワクしますね！")

    for category, cat_name in CATEGORIES_JA.items():
        articles = selected.get(category, [])
        if not articles:
            continue

        lines.append(f"[てらこ先生] では、{cat_name}関連のニュースをお届けします。")
        lines.append(f"[ミカ] {cat_name}、気になりますね。")

        for art in articles:
            title   = preprocess_for_tts(clean_text(
                art.get("title_ja") or art.get("title_en") or ""
            ))
            summary = preprocess_for_tts(clean_text(art.get("summary") or ""))
            source  = preprocess_for_tts(clean_text(art.get("source") or ""))
            if summary in ("Read the full article for details.", "詳細は記事をご覧ください。"):
                summary = ""

            title_clean = title.rstrip("。．.")
            intro = f"{title_clean}。"
            if source:
                intro += f"{source}からのニュースです。"
            if summary and len(summary) <= 250:
                intro += summary

            lines.append(f"[てらこ先生] {intro}")
            lines.append(f"[ミカ] これは注目ですね。もう少し詳しく教えてもらえますか？")
            detail = summary[:150] if summary else "引き続き動向を注視していきます。"
            lines.append(f"[てらこ先生] そうですね。{detail}　今後の展開が注目されます。")

    lines.append(f"[ミカ] 今日も盛りだくさんの内容でしたね！")
    lines.append(
        f"[てらこ先生] 以上、{date_str}版の注目{total}件をお届けしました。"
        "てらこAIニュースダイジェスト、また明日もお楽しみに。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 台本パーサー
# ---------------------------------------------------------------------------

def parse_dialogue(script: str) -> List[Tuple[str, str]]:
    """
    [てらこ先生] テキスト / [ミカ] テキスト 形式を
    [(speaker, text), ...] のリストに変換する。
    """
    segments: List[Tuple[str, str]] = []
    # 改行区切りで走査
    for line in script.splitlines():
        line = line.strip()
        m = re.match(r"^\[(てらこ先生|ミカ)\]\s*(.+)$", line)
        if m:
            speaker = m.group(1)
            text    = m.group(2).strip()
            if text:
                segments.append((speaker, text))
    return segments


# ---------------------------------------------------------------------------
# edge-tts 非同期 TTS（セグメント単位）
# ---------------------------------------------------------------------------

async def _tts_segment_async(text: str, voice: str, output_path: Path,
                              rate: str = "+0%", pitch: str = "+0Hz") -> None:
    import edge_tts
    communicate = edge_tts.Communicate(
        preprocess_for_tts(text),
        voice,
        rate=rate,
        pitch=pitch,
    )
    await communicate.save(str(output_path))


def _voice_params_for(speaker: str) -> Dict[str, str]:
    """話者ごとの voice/rate/pitch を返す。未定義話者は てらこ先生 と同じ。"""
    return VOICE_PARAMS.get(speaker, VOICE_PARAMS["てらこ先生"])


def _run_async(coro):
    """イベントループの状態に依らず非同期コルーチンを実行するヘルパー。"""
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
# pydub でセグメント結合
# ---------------------------------------------------------------------------

def _generate_dialogue_audio(
    segments: List[Tuple[str, str]],
    output_file: Path,
) -> bool:
    """
    各セグメントを edge-tts で合成し結合 → output_file に書き出す。
    pydub が利用可能ならそれを使い、Python 3.13+ 環境など使えない場合は
    ffmpeg を直接呼び出す。
    """
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("  ⚠️  edge-tts 未インストール。pip install edge-tts")
        return False

    # pydub が使えるか試みる（Python 3.13+ では audioop/pyaudioop が必要）
    _pydub_available = False
    try:
        from pydub import AudioSegment  # noqa: F401
        _pydub_available = True
    except Exception:
        pass

    if _pydub_available:
        return _concat_with_pydub(segments, output_file)
    else:
        return _concat_with_ffmpeg(segments, output_file)


def _concat_with_pydub(segments: List[Tuple[str, str]], output_file: Path) -> bool:
    """pydub を使った音声結合（Python ≤ 3.12 推奨）。
    出力は 44.1kHz stereo 80kbps の最も互換性の高い MP3。"""
    from pydub import AudioSegment

    sil_same   = AudioSegment.silent(duration=SILENCE_SAME_SPEAKER)
    sil_change = AudioSegment.silent(duration=SILENCE_SPEAKER_CHANGE)
    combined    = AudioSegment.empty()
    prev_speaker = ""
    ok_count     = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (speaker, text) in enumerate(segments):
            p        = _voice_params_for(speaker)
            tmp_file = Path(tmpdir) / f"seg_{i:04d}.mp3"
            try:
                _run_async(_tts_segment_async(
                    text, p["voice"], tmp_file,
                    rate=p["rate"], pitch=p["pitch"],
                ))
                seg_audio = AudioSegment.from_mp3(str(tmp_file))
                if prev_speaker:
                    combined += (sil_change if prev_speaker != speaker else sil_same)
                combined    += seg_audio
                prev_speaker = speaker
                ok_count    += 1
                if (i + 1) % 10 == 0:
                    print(f"    ... {i + 1}/{len(segments)} セグメント完了")
            except Exception as e:
                print(f"  ⚠️  セグメント{i}（{speaker}）スキップ: {e}")

        if ok_count == 0 or len(combined) == 0:
            print("  ❌ 全セグメントが失敗しました（pydub）")
            return False

        # 44.1kHz stereo に強制変換してエクスポート（プレイヤー互換性最大化）
        combined = combined.set_frame_rate(44100).set_channels(2)
        combined.export(
            str(output_file),
            format="mp3",
            bitrate="80k",
            parameters=["-write_xing", "1", "-id3v2_version", "3"],
        )
        print(f"  ✓ 結合完了（pydub, 44.1kHz stereo 80k）: {ok_count}/{len(segments)} セグメント")
    return True


def _concat_with_ffmpeg(segments: List[Tuple[str, str]], output_file: Path) -> bool:
    """ffmpeg subprocess を直接呼び出す音声結合（Python 3.13+ 対応）。

    プレイヤー互換性のため 2 パス方式：
      1. 全セグメントを concat フィルタで PCM ストリームとして結合
      2. 44.1kHz stereo 80kbps の単一の MP3 として再エンコード
    """
    import subprocess
    import shutil

    if not shutil.which("ffmpeg"):
        print("  ⚠️  ffmpeg が見つかりません。brew install ffmpeg でインストールしてください")
        return False

    ok_count    = 0
    prev_speaker = ""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # -- 無音ファイルを生成（24kHz mono は edge-tts と一致させる）--
        sil_short = tmpdir_path / "sil_short.mp3"
        sil_long  = tmpdir_path / "sil_long.mp3"
        for sil_file, duration in [(sil_short, "0.25"), (sil_long, "0.5")]:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", duration,
                "-codec:a", "libmp3lame", "-b:a", "64k",
                str(sil_file),
            ], capture_output=True, check=True)

        # -- セグメント生成 & concat リスト作成 --
        concat_entries: List[Path] = []
        for i, (speaker, text) in enumerate(segments):
            p        = _voice_params_for(speaker)
            seg_file = tmpdir_path / f"seg_{i:04d}.mp3"
            try:
                _run_async(_tts_segment_async(
                    text, p["voice"], seg_file,
                    rate=p["rate"], pitch=p["pitch"],
                ))
                if prev_speaker:
                    concat_entries.append(
                        sil_long if prev_speaker != speaker else sil_short
                    )
                concat_entries.append(seg_file)
                prev_speaker = speaker
                ok_count    += 1
                if (i + 1) % 10 == 0:
                    print(f"    ... {i + 1}/{len(segments)} セグメント完了")
            except Exception as e:
                print(f"  ⚠️  セグメント{i}（{speaker}）スキップ: {e}")

        if ok_count == 0:
            print("  ❌ 全セグメントが失敗しました（ffmpeg）")
            return False

        # -- concat.txt を書き出す --
        concat_list = tmpdir_path / "concat.txt"
        with open(concat_list, "w") as f:
            for entry in concat_entries:
                f.write(f"file '{str(entry)}'\n")

        # -- パス1: concat → 中間 MP3 (24kHz mono) --
        intermediate = tmpdir_path / "intermediate.mp3"
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-codec:a", "libmp3lame", "-b:a", "64k",
            str(intermediate),
        ], capture_output=True)
        if result.returncode != 0:
            print(f"  ❌ ffmpeg concat エラー: {result.stderr.decode()[-300:]}")
            return False

        # -- パス2: 44.1kHz stereo 80kbps にクリーン再エンコード（プレイヤー互換性） --
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", str(intermediate),
            "-ar", "44100",
            "-ac", "2",
            "-codec:a", "libmp3lame",
            "-b:a", "80k",
            "-write_xing", "1",
            "-id3v2_version", "3",
            str(output_file),
        ], capture_output=True)
        if result.returncode != 0:
            print(f"  ❌ ffmpeg 再エンコードエラー: {result.stderr.decode()[-300:]}")
            return False

        print(f"  ✓ 結合完了（ffmpeg, 44.1kHz stereo 80k）: {ok_count}/{len(segments)} セグメント")
    return True


# ---------------------------------------------------------------------------
# 公開エントリーポイント（generate_podcast.py と同じシグネチャ）
# ---------------------------------------------------------------------------

def generate_podcast(articles_by_category: Dict[str, List[Dict]], date: datetime) -> bool:
    PODCAST_DIR.mkdir(exist_ok=True)
    date_str = date.strftime("%Y-%m-%d")

    # 1. 台本生成（Gemini or フォールバック）
    print("  対話型台本を生成中...")
    script = build_dialogue_script(articles_by_category, date)

    script_file = PODCAST_DIR / f"script-{date_str}.txt"
    script_file.write_text(script, encoding="utf-8")
    print(f"  ✓ 台本保存: {script_file.name}")

    # 2. 台本パース
    segments = parse_dialogue(script)
    if not segments:
        print("  ❌ 台本のパースに失敗しました（[てらこ先生]/[ミカ] 行が見つからない）")
        return False

    terako_count = sum(1 for s, _ in segments if s == "てらこ先生")
    mika_count   = sum(1 for s, _ in segments if s == "ミカ")
    print(f"  ✓ セグメント数: {len(segments)} （てらこ先生: {terako_count} / ミカ: {mika_count}）")

    # 3. 音声合成 + 結合
    output_file = PODCAST_DIR / f"ai-news-{date_str}.mp3"
    print(f"  音声合成中（{len(segments)} セグメント）…")
    success = _generate_dialogue_audio(segments, output_file)

    if not success or not output_file.exists() or output_file.stat().st_size == 0:
        print("  ❌ 音声生成に失敗しました")
        return False

    size_mb = output_file.stat().st_size / 1_048_576
    print(f"  ✓ {output_file.name} ({size_mb:.1f} MB)")
    print(f"  📁 ローカル: {output_file.resolve()}")
    print(f"  🌐 公開URL: {BASE_URL}/podcast/{output_file.name}")

    # 4. RSS フィード更新
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
            {
                "title_ja": "オープンエーアイ、推論能力が向上した新モデルを発表",
                "title_en": "OpenAI releases GPT-5 with improved reasoning",
                "summary": "複数ステップの推論とコーディングタスクで従来比40パーセント改善。医療診断や法律文書の解析にも活用可能とされています。",
                "source": "TechCrunch",
                "importance": 3,
            },
        ],
        "research": [
            {
                "title_ja": "Google、AIで膵臓がんを最大3年早期発見",
                "title_en": "Google AI detects pancreatic cancer 3 years earlier",
                "summary": "Google DeepMindの新モデルが従来の検査では見逃していた患者の35パーセントを、3年前の段階で検出できると発表。",
                "source": "Nature",
                "importance": 3,
            },
        ],
        "business": [
            {
                "title_ja": "アンソロピック、評価額9000億ドルで新たな資金調達へ",
                "title_en": "Anthropic raises at $900B valuation",
                "summary": "AI安全企業のアンソロピックが評価額9000億ドルで新たな資金調達ラウンドを検討。",
                "source": "VentureBeat",
                "importance": 2,
            },
        ],
    }
    success = generate_podcast(test_data, date)
    print("✅ Done" if success else "❌ Failed")
