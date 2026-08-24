# CLAUDE.md

このファイルはClaude(VSCode拡張・CLI・Web版すべて)が読むプロジェクトルールです。
どの環境で作業しても、ここに書いたルールが共通で適用されます。
ルールを追加・変更したら、コミットしてプッシュすれば全環境に反映されます。

## プロジェクト概要

てらこAIニュースダイジェスト。毎日のAIニュースをHTML・ポッドキャスト音声・動画で配信するプロジェクト。

- `generate_news.py` — 日次ニュースHTML (`ai-news-YYYY-MM-DD.html`) を生成
- `generate_podcast.py` / `generate_podcast_dialogue.py` — ポッドキャスト音声 (`podcast/`) を生成
- `send_email.py` — メール配信
- `remotion/` — Remotionによる動画生成 (Node.js/React。詳細は `remotion/README.md`)
- `.github/workflows/generate-news.yml` — 毎日 UTC 21:00 (JST 朝6:00) に自動実行

## このフォルダ（ローカル環境）についての注意

**ローカルのフォルダ名は `~/teraco-labo-website` だが、ホームページではない。**
GitHubの接続先は `teraco-labo/ai-news-digest`、中身は日々のAIニュースHTMLと生成スクリプト。

- ホームページの正規リポジトリは `~/Documents/GitHub/teraco-labo-website-v2`
- **このローカルフォルダの名前は変更しないこと。** 自動処理（launchd / GitHub Actions）がこのパスを見ている
- AIニュース以外の案件は、**すべて `~/Documents/GitHub/<プロジェクト名>/` に新しくフォルダを作って**そちらで作業すること。過去にここへ紛れ込んだ別案件（顧客管理・FINSスケジューラー・LINE配信・スマホ講座スライド）は 2026-08-18 に `~/Documents/GitHub/` へ救出済み。ここに残っているのは元データ
- `pwa-reserve/` `customer-tool/` `teraco-voice-v2/` も本来ここの住人ではない

## 注意点

- 日付は必ずJST基準で判定する (GitHub ActionsはUTCで動くため。`generate_news.py` 冒頭参照)
- Python依存は `requirements.txt`、Remotion側の依存は `remotion/package.json` で管理
- `remotion/node_modules/` と `remotion/out/` はコミットしない

## 動画作成 (Remotion)

- 動画の依頼は `remotion/PROMPT_TEMPLATE.md` のテンプレートを使う
- コンポジションは `remotion/src/` に追加し、`Root.tsx` に登録する
- レンダリング確認は静止画 (`npx remotion still`) で素早く行い、最後にmp4を出力する

## ルール

<!-- ここに作業ルールを追記していく。例: -->
<!-- - コミットメッセージは日本語で書く -->
<!-- - 動画のデフォルト配色は紫系グラデーション (#667eea → #764ba2) -->
