import {Composition} from 'remotion';
import {NewsDigest, newsDigestSchema} from './NewsDigest';
import {SnsShort, snsShortSchema} from './SnsShort';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="NewsDigest"
        component={NewsDigest}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        schema={newsDigestSchema}
        defaultProps={{
          date: '2026-07-16',
          headlines: [
            'OpenAIが新モデルを発表',
            'GoogleがGemini最新版を公開',
            'AnthropicがClaude 5ファミリーをリリース',
          ],
        }}
      />
      <Composition
        id="SnsShort"
        component={SnsShort}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        schema={snsShortSchema}
        defaultProps={{
          title: '今日のAIニュース',
          date: '2026-07-16',
          headlines: [
            'OpenAI、Codex向けに230ドルのキーボードを発売',
            'Thinking Machines、初のオープンモデル「Inkling」を公開',
            'AI音楽のSuno、YouTubeスクレイピング疑惑が浮上',
          ],
          outroLine1: '毎朝配信中',
          outroLine2: 'リンクはプロフィールから',
        }}
      />
    </>
  );
};
