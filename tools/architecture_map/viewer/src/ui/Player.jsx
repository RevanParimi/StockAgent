import { forwardRef } from 'react';
import { MODES, SPEEDS, captionOf, daysOf } from '../lib/play.js';

const Name = ({ children }) => <strong className="player-name">{children}</strong>;

/** The bar under the world that plays a mode: where it is, the step's words, Back, Play or
 *  Pause, Next, the speed and Close; on the clock also a slider over the day's times.
 *  `primary` is the button that takes the focus when a mode is opened. */
const Player = forwardRef(function Player({
  mode, steps, step, lights, lightsShown, playing, speed, onBack, onNext, onPlay, onSpeed,
  onSeek, onClose,
}, primary) {
  const { title } = MODES[mode];
  const { lead, name, text } = captionOf(mode, steps[step]);
  const last = step === steps.length - 1;
  const clock = mode === 'clock';
  // A trace or tour ends on its last step; the clock's day just ends there.
  const finish = last && !clock;
  // `aria-disabled` rather than `disabled`: a button that has the focus keeps it.
  const noBack = step === 0;
  const noNext = clock && last;
  const at = (i) => `${steps[i].time}, ${daysOf(steps[i].job)}, ${steps[i].job.name}`;
  return (
    <section className="player" aria-label={title} data-player={mode}>
      <div className="player-head">
        <h2>{title}</h2>
        <span className="count">{step + 1} of {steps.length}</span>
      </div>
      {/* said politely, so a screen reader follows autoplay */}
      <p className="player-caption" role="status">
        {lead ? <span className="lead">{lead}</span> : null}
        {name ? <Name>{name}</Name> : null}
        <span>{text}</span>
      </p>
      {/* in words for those who cannot see the map; without a 3D view, for everyone. The
          clock's panel lists the same */}
      {!clock && lights.length ? (
        <p className={lightsShown ? 'player-lights' : 'sr-only'}>
          Highlighted on the map: {lights.join(', ')}.</p>
      ) : null}
      {clock ? (
        <div className="timeline">
          <span className="tabular" aria-hidden="true">{steps[0].time}</span>
          <input type="range" min={0} max={steps.length - 1} step={1} value={step}
            aria-label="Time of day" aria-valuetext={at(step)}
            onChange={(e) => onSeek(Number(e.target.value))} />
          <span className="tabular" aria-hidden="true">{steps[steps.length - 1].time}</span>
        </div>
      ) : null}
      <div className="player-controls">
        <button type="button" onClick={noBack ? undefined : onBack} aria-disabled={noBack}>
          ← Back</button>
        <button type="button" onClick={onPlay} aria-pressed={playing}
          ref={clock ? primary : undefined}>{playing ? 'Pause' : 'Play'}</button>
        <button type="button" onClick={finish ? onClose : noNext ? undefined : onNext}
          aria-disabled={noNext} ref={clock ? undefined : primary}>
          {finish ? 'Finish' : 'Next →'}</button>
        <div className="segmented" role="group" aria-label="Autoplay speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" aria-pressed={speed === s} onClick={() => onSpeed(s)}>
              {s}×</button>
          ))}
        </div>
        <button type="button" className="player-close" onClick={onClose}
          aria-label={`Close ${title}`}>Close ✕ <kbd aria-hidden="true">Esc</kbd></button>
      </div>
    </section>
  );
});

export default Player;
