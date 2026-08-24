import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {z} from 'zod';

export const snsShortSchema = z.object({
  title: z.string(),
  date: z.string(),
  headlines: z.array(z.string()),
  outroLine1: z.string(),
  outroLine2: z.string(),
});

type SnsShortProps = z.infer<typeof snsShortSchema>;

const CYAN = '#00e5ff';
const MAGENTA = '#ff2ec4';

const neonGlow = (color: string) =>
  `0 0 12px ${color}, 0 0 40px ${color}66, 0 0 80px ${color}33`;

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = frame * 0.4;
  return (
    <AbsoluteFill style={{background: '#050508'}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(600px at ${20 + drift * 0.1}% 15%, ${CYAN}22, transparent 70%),
                       radial-gradient(700px at 85% ${80 - drift * 0.05}%, ${MAGENTA}22, transparent 70%)`,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `repeating-linear-gradient(0deg, transparent 0px, transparent 3px, #ffffff05 3px, #ffffff05 4px)`,
        }}
      />
    </AbsoluteFill>
  );
};

const PunchIn: React.FC<{children: React.ReactNode; durationInFrames: number}> = ({
  children,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const punch = spring({frame, fps, config: {damping: 14, stiffness: 160}});
  const scale = interpolate(punch, [0, 1], [1.7, 1]);
  const slowZoom = 1 + frame * 0.0012;
  const exit = interpolate(
    frame,
    [durationInFrames - 10, durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        padding: 80,
        opacity: punch * exit,
        transform: `scale(${scale * slowZoom})`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const SnsShort: React.FC<SnsShortProps> = ({
  title,
  date,
  headlines,
  outroLine1,
  outroLine2,
}) => {
  const {durationInFrames} = useVideoConfig();
  const introDur = 90;
  const outroDur = 90;
  const perHeadline = Math.floor(
    (durationInFrames - introDur - outroDur) / headlines.length,
  );

  return (
    <AbsoluteFill style={{fontFamily: 'sans-serif', color: 'white'}}>
      <Background />

      <Sequence durationInFrames={introDur}>
        <PunchIn durationInFrames={introDur}>
          <div style={{textAlign: 'center'}}>
            <div
              style={{
                fontSize: 100,
                fontWeight: 900,
                lineHeight: 1.2,
                textShadow: neonGlow(CYAN),
              }}
            >
              {title}
            </div>
            <div
              style={{
                fontSize: 44,
                marginTop: 30,
                letterSpacing: '0.2em',
                color: MAGENTA,
                textShadow: neonGlow(MAGENTA),
              }}
            >
              {date}
            </div>
          </div>
        </PunchIn>
      </Sequence>

      {headlines.map((headline, i) => (
        <Sequence
          key={i}
          from={introDur + i * perHeadline}
          durationInFrames={perHeadline}
        >
          <PunchIn durationInFrames={perHeadline}>
            <div style={{textAlign: 'center', maxWidth: 900}}>
              <div
                style={{
                  display: 'inline-block',
                  fontSize: 40,
                  fontWeight: 700,
                  color: '#050508',
                  background: i % 2 === 0 ? CYAN : MAGENTA,
                  padding: '8px 34px',
                  borderRadius: 999,
                  marginBottom: 44,
                  boxShadow: neonGlow(i % 2 === 0 ? CYAN : MAGENTA),
                }}
              >
                {String(i + 1).padStart(2, '0')}
              </div>
              <div
                style={{
                  fontSize: 66,
                  fontWeight: 800,
                  lineHeight: 1.45,
                  textShadow: '0 4px 30px #000000cc',
                }}
              >
                {headline}
              </div>
            </div>
          </PunchIn>
        </Sequence>
      ))}

      <Sequence from={durationInFrames - outroDur}>
        <PunchIn durationInFrames={outroDur}>
          <div style={{textAlign: 'center'}}>
            <div
              style={{
                fontSize: 80,
                fontWeight: 900,
                textShadow: neonGlow(MAGENTA),
              }}
            >
              {outroLine1}
            </div>
            <div style={{fontSize: 46, marginTop: 36, color: CYAN, textShadow: neonGlow(CYAN)}}>
              {outroLine2}
            </div>
          </div>
        </PunchIn>
      </Sequence>
    </AbsoluteFill>
  );
};
