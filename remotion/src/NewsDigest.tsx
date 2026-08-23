import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {z} from 'zod';

export const newsDigestSchema = z.object({
  date: z.string(),
  headlines: z.array(z.string()),
});

type NewsDigestProps = z.infer<typeof newsDigestSchema>;

export const NewsDigest: React.FC<NewsDigestProps> = ({date, headlines}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const titleScale = spring({frame, fps, config: {damping: 200}});
  const titleOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        fontFamily: 'sans-serif',
        color: 'white',
        padding: 100,
      }}
    >
      <h1
        style={{
          fontSize: 90,
          opacity: titleOpacity,
          transform: `scale(${titleScale})`,
          marginBottom: 10,
        }}
      >
        てらこAIニュースダイジェスト
      </h1>
      <h2 style={{fontSize: 50, opacity: titleOpacity, marginBottom: 60}}>
        {date}
      </h2>
      {headlines.map((headline, i) => {
        const delay = 30 + i * 20;
        const progress = spring({
          frame: frame - delay,
          fps,
          config: {damping: 200},
        });
        return (
          <div
            key={i}
            style={{
              fontSize: 48,
              marginBottom: 30,
              opacity: progress,
              transform: `translateX(${(1 - progress) * 100}px)`,
            }}
          >
            ・{headline}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
