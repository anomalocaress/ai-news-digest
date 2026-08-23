import {Composition} from 'remotion';
import {NewsDigest, newsDigestSchema} from './NewsDigest';

export const RemotionRoot: React.FC = () => {
  return (
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
  );
};
