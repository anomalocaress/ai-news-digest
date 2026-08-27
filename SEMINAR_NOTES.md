# セミナー録画を「AIに質問できる状態」にする

Zoom で講座をやって録画し、あとから議事録・タイムスタンプ付き要約を作り、
内容について AI に質問する——そのための手順とツールのまとめです。

## なぜ NotebookLM に YouTube を貼ると弾かれるのか

NotebookLM の YouTube ソースには条件があります。

| 条件 | 内容 |
|---|---|
| 公開範囲 | **一般公開**の動画のみ。限定公開・非公開は対象外 |
| 字幕 | **字幕（自動生成でも可）が付いている**こと。無い動画は追加できない |
| 経過時間 | 投稿から **72時間**以内はインポートに失敗することがある |
| 取り込む中身 | **字幕テキストだけ**。映像・音声は読まれない |

重要なのは最後の行です。**NotebookLM は動画を文字起こししていません。**
YouTube が持っている字幕データをそのまま取り込んでいるだけなので、
字幕が無ければ渡すものが無く、エラーになります。

セミナー録画はふつう限定公開にするので、この時点で条件から外れます。
「YouTubeぶっこんでも認識できない」のはこれが理由で、設定の問題ではありません。

**回避策は昔から決まっていて「文字起こしをテキストとして渡す」です。**
限定公開のままでも、文字起こしのテキストなら NotebookLM のソースにできます。

## このリポジトリのツール

`seminar_notes.py` が、文字起こしを取ってくるところから議事録を書くところまでやります。

```bash
pip install -r requirements.txt

# 録画から一式（文字起こし＋議事録）を作る
python seminar_notes.py https://youtu.be/XXXXXXXXXXX --title "第3回 社内勉強会"

# 手元に録画ファイルがあるならそれでもいい（Zoomのローカル録画など）
python seminar_notes.py ./recording.m4a --title "Zoom録画（2026-08-27）"

# 限定公開でログインが要る場合はブラウザのCookieを借りる
python seminar_notes.py <URL> --cookies-from-browser chrome

# できたものに質問する（NotebookLMの代わり）
python seminar_notes.py --ask "MCP版とAPI版の違いは？"
python seminar_notes.py --ask "料金の話はどこ？" --slug 2026-08-27-勉強会

# 重点を指定する（ツールの使い方が中心の回など）
python seminar_notes.py <URL> --title "..." --focus "ツールの使い方を手順まで詳しく"

# 保存済みの一覧
python seminar_notes.py --list
```

### 出力

`seminars/<スラッグ>/` に3つ出ます。

- **`transcript.txt`** — タイムスタンプ付きの文字起こし。
  これを NotebookLM の「テキストを貼り付け」に渡せば、限定公開のままソースにできます
- **`notes.md`** — 議事録・タイムスタンプ付き要約・決まったこと・
  ネクストアクション・**参加者への配布メール文面**。
  ツールの操作説明があった回は **「ツールの使い方」** も付きます
  （番号付きの手順＋各手順のタイムスタンプ＋設定値の原文＋つまずきポイント）
- **`meta.json`** — 元URL・取得方法・文字数の記録

セミナーの中身は社外に出せないことが多いので、`seminars/` は `.gitignore` 済みです。

### 文字起こしの取り方

上から順に試して、通ったところで止まります。

1. **YouTube の字幕を API で取得** — 限定公開でも字幕さえあれば通る。無料・数秒
2. **yt-dlp で自動生成字幕を取得** — 1が塞がれたときの予備
3. **音声をダウンロードして Gemini で文字起こし** — 字幕が無い動画・ローカル録画用

3 だけ API キーが要ります（`GEMINI_API_KEY`。予備で `OPENAI_API_KEY`）。
1・2 は鍵なしで動きます。

議事録の作成と質問への回答は Claude が担当します。`claude` CLI がログイン済みなら
サブスクリプションの枠で動き、無ければ `ANTHROPIC_API_KEY` の従量課金に落ちます
（`curate.py` と同じ仕組み）。

## 運用の流れ

1. Zoom で録画（クラウド録画でもローカル録画でもよい）
2. YouTube に**限定公開**でアップ、または録画ファイルをそのまま使う
3. `python seminar_notes.py <URL or ファイル> --title "..."`
4. `notes.md` の議事録を Google ドキュメントに貼って、必要なら手直しする
5. `notes.md` の末尾にあるメール文面に、議事録URLと録画URLを差し込んで送る
6. あとから内容を確認したくなったら `--ask` で質問する。
   NotebookLM を使いたい場合は `transcript.txt` をソースとして貼り付ける

## つまずきどころ

| 症状 | 対処 |
|---|---|
| 字幕APIで取れない | 動画に字幕が無い。`--audio` で音声から文字起こしする |
| 限定公開でダウンロードできない | `--cookies-from-browser chrome` でログイン状態を借りる |
| 音声の文字起こしが失敗する | `GEMINI_API_KEY` を設定する。OpenAI 側は1ファイル25MB上限で長時間録画に向かない |
| 議事録が作られない | `claude` CLI がログイン済みか、`ANTHROPIC_API_KEY` があるか確認する |
| 話者が「講師」「参加者」になる | 音声からの文字起こしは話者名を推測できない。`notes.md` で手で直す |

## 参考

- [Add or discover new sources for your notebook — Gemini Notebook Help](https://support.google.com/gemininotebook/answer/16215270?hl=en&co=GENIE.Platform%3DDesktop)
- [限定公開YouTube動画をNotebookLMに渡す「無理のない」運用術（Zenn / SoftBank）](https://zenn.dev/softbank/articles/22ef4a4bc3aec4)
- [NotebookLMで動画を読み込む方法｜YouTube・MP4・200MB超の対処法](https://skillstack-lab.com/notebooklm-video/)
