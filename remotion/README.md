# Remotion 動画生成

AIニュースダイジェストの動画を [Remotion](https://www.remotion.dev/) で生成するプロジェクトです。

## セットアップ

```bash
cd remotion
npm install
```

## 使い方

```bash
# プレビュー (Remotion Studio をブラウザで開く)
npm run dev

# 動画をレンダリング (out/news-digest.mp4)
npm run render

# サムネイル静止画を生成 (out/thumbnail.png)
npm run still
```

日付や見出しは props で差し替えられます:

```bash
npx remotion render NewsDigest out/news-digest.mp4 \
  --props='{"date":"2026-07-16","headlines":["見出し1","見出し2"]}'
```

## 構成

- `src/index.ts` — エントリポイント (registerRoot)
- `src/Root.tsx` — コンポジション定義 (1920x1080 / 30fps / 10秒)
- `src/NewsDigest.tsx` — ニュースダイジェスト動画のコンポーネント (zod スキーマで props を定義)
- `remotion.config.ts` — レンダリング設定

## 備考

- Chrome がローカルにない場合、Remotion が自動で Chrome Headless Shell をダウンロードします。
- 既存の Chromium/headless_shell を使う場合は `--browser-executable=<パス>` を指定してください。
