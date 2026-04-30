/*
 * ═══════════════════════════════════════════════════════════════
 *  PandaCharacter.tsx
 *  Detailed Kung Fu Panda-style SVG character.
 *  Every major body part is a separate <g> with a class so
 *  PandaAnimations.css can animate them independently.
 * ═══════════════════════════════════════════════════════════════
 */

export type PandaState = 'idle' | 'excited' | 'thinking' | 'worried'

interface Props {
  state?: PandaState
  size?: number   // controls width; height scales proportionally (300×420 viewBox)
  style?: React.CSSProperties
}

export function PandaCharacter({ state = 'idle', size = 340, style }: Props) {
  const stateClass =
    state === 'excited'  ? 'panda-excited'  :
    state === 'thinking' ? 'panda-thinking' :
    state === 'worried'  ? 'panda-worried'  : ''

  return (
    <svg
      viewBox="0 0 300 420"
      width={size}
      height={size * (420 / 300)}
      xmlns="http://www.w3.org/2000/svg"
      className={stateClass}
      style={{ overflow: 'visible', ...style }}
      aria-hidden="true"
    >
      <defs>
        {/* Radial glow behind panda */}
        <radialGradient id="pandaBgGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#BFDBFE" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#EFF6FF"  stopOpacity="0" />
        </radialGradient>
        {/* Soft face gradient */}
        <radialGradient id="faceGrad" cx="50%" cy="40%" r="58%">
          <stop offset="0%"   stopColor="#FFFFFF" />
          <stop offset="100%" stopColor="#F0F4FF" />
        </radialGradient>
        {/* Body gradient */}
        <radialGradient id="bodyGrad" cx="50%" cy="35%" r="60%">
          <stop offset="0%"   stopColor="#FFFFFF" />
          <stop offset="100%" stopColor="#E8EFFF" />
        </radialGradient>
        {/* Eye iris gradient — jade green like KFP */}
        <radialGradient id="irisGrad" cx="35%" cy="35%" r="65%">
          <stop offset="0%"   stopColor="#4ADE80" />
          <stop offset="100%" stopColor="#15803D" />
        </radialGradient>
        {/* Drop shadow filter */}
        <filter id="pandaShadow" x="-20%" y="-10%" width="140%" height="130%">
          <feDropShadow dx="0" dy="8" stdDeviation="12" floodColor="#93C5FD" floodOpacity="0.35" />
        </filter>
        <filter id="softShadow" x="-10%" y="-5%" width="120%" height="115%">
          <feDropShadow dx="0" dy="3" stdDeviation="5" floodColor="#1E3A8A" floodOpacity="0.12" />
        </filter>
      </defs>

      {/* ── Ambient glow circle ── */}
      <circle
        className="panda-glow"
        cx="150" cy="210"
        r="115"
        fill="url(#pandaBgGlow)"
      />

      {/* ══════════ BODY GROUP (breathes) ══════════ */}
      <g className="panda-body" filter="url(#pandaShadow)">

        {/* Black shoulder/back — left */}
        <ellipse cx="82"  cy="272" rx="38" ry="52"
          fill="#1C1C1C" transform="rotate(-8,82,272)" />
        {/* Black shoulder/back — right */}
        <ellipse cx="218" cy="272" rx="38" ry="52"
          fill="#1C1C1C" transform="rotate(8,218,272)" />

        {/* Main white body */}
        <ellipse cx="150" cy="305" rx="82" ry="98"
          fill="url(#bodyGrad)" />

        {/* Belly highlight ring */}
        <ellipse cx="150" cy="310" rx="50" ry="60"
          fill="white" opacity="0.55" />

        {/* Martial-arts belt — warm brown */}
        <rect x="100" y="292" width="100" height="22" rx="11"
          fill="#78491A" filter="url(#softShadow)" />
        {/* Belt buckle */}
        <rect x="134" y="288" width="32" height="30" rx="7"
          fill="#5C3410" />
        {/* Buckle inset */}
        <rect x="140" y="294" width="20" height="18" rx="4"
          fill="#8B5E2A" />
        <circle cx="150" cy="303" r="3" fill="#D4A05A" />

        {/* Left leg */}
        <ellipse cx="115" cy="396" rx="28" ry="18"
          fill="#1C1C1C" />
        {/* Right leg */}
        <ellipse cx="185" cy="396" rx="28" ry="18"
          fill="#1C1C1C" />

        {/* Left foot toes */}
        <circle cx="100" cy="400" r="5.5" fill="#2A2A2A" />
        <circle cx="112" cy="403" r="5.5" fill="#2A2A2A" />
        <circle cx="124" cy="403" r="5.5" fill="#2A2A2A" />
        {/* Right foot toes */}
        <circle cx="174" cy="403" r="5.5" fill="#2A2A2A" />
        <circle cx="186" cy="403" r="5.5" fill="#2A2A2A" />
        <circle cx="198" cy="400" r="5.5" fill="#2A2A2A" />

      </g>

      {/* ══════════ LEFT ARM GROUP ══════════ */}
      <g className="panda-arm-l">
        {/* Upper arm */}
        <ellipse cx="68" cy="300" rx="22" ry="52"
          fill="#1C1C1C" transform="rotate(-14,85,268)" />
        {/* Forearm bulge */}
        <ellipse cx="50" cy="348" rx="18" ry="26"
          fill="#1C1C1C" transform="rotate(-5,50,348)" />
        {/* Paw pad */}
        <ellipse cx="42" cy="370" rx="20" ry="13"
          fill="#1C1C1C" />
        {/* Paw toes */}
        <circle cx="30" cy="364" r="5"  fill="#2A2A2A" />
        <circle cx="40" cy="360" r="5"  fill="#2A2A2A" />
        <circle cx="51" cy="361" r="5"  fill="#2A2A2A" />
        <circle cx="56" cy="369" r="4"  fill="#2A2A2A" />
      </g>

      {/* ══════════ RIGHT ARM GROUP ══════════ */}
      <g className="panda-arm-r">
        {/* Upper arm */}
        <ellipse cx="232" cy="300" rx="22" ry="52"
          fill="#1C1C1C" transform="rotate(14,215,268)" />
        {/* Forearm bulge */}
        <ellipse cx="250" cy="348" rx="18" ry="26"
          fill="#1C1C1C" transform="rotate(5,250,348)" />
        {/* Paw pad */}
        <ellipse cx="258" cy="370" rx="20" ry="13"
          fill="#1C1C1C" />
        {/* Paw toes */}
        <circle cx="246" cy="369" r="4"  fill="#2A2A2A" />
        <circle cx="249" cy="361" r="5"  fill="#2A2A2A" />
        <circle cx="260" cy="360" r="5"  fill="#2A2A2A" />
        <circle cx="270" cy="364" r="5"  fill="#2A2A2A" />
      </g>

      {/* ══════════ HEAD GROUP (floats) ══════════ */}
      <g className="panda-head" filter="url(#pandaShadow)">

        {/* Left ear — outer */}
        <g className="panda-ear-l">
          <ellipse cx="72" cy="68" rx="34" ry="31" fill="#1C1C1C" />
          {/* Inner ear */}
          <ellipse cx="72" cy="70" rx="20" ry="18" fill="#2D2D2D" />
        </g>

        {/* Right ear — outer */}
        <g className="panda-ear-r">
          <ellipse cx="228" cy="68" rx="34" ry="31" fill="#1C1C1C" />
          {/* Inner ear */}
          <ellipse cx="228" cy="70" rx="20" ry="18" fill="#2D2D2D" />
        </g>

        {/* Main face oval */}
        <ellipse cx="150" cy="152" rx="95" ry="90" fill="url(#faceGrad)" />

        {/* ── Eye patches (KFP signature: large teardrop shapes) ── */}
        {/* Left patch */}
        <ellipse cx="108" cy="143"
          rx="40" ry="30"
          fill="#1C1C1C"
          transform="rotate(-20,108,143)" />
        {/* Right patch */}
        <ellipse cx="192" cy="143"
          rx="40" ry="30"
          fill="#1C1C1C"
          transform="rotate(20,192,143)" />

        {/* ── Left eye (animates blink) ── */}
        <g className="panda-eye-l">
          {/* Sclera */}
          <circle cx="108" cy="143" r="21" fill="white" />
          {/* Iris — jade green */}
          <circle cx="108" cy="143" r="14" fill="url(#irisGrad)" />
          {/* Pupil */}
          <circle cx="110" cy="145" r="9"  fill="#0A0A0A" />
          {/* Primary highlight */}
          <circle cx="103" cy="138" r="4"  fill="white" opacity="0.9" />
          {/* Secondary micro-highlight */}
          <circle cx="114" cy="150" r="2"  fill="white" opacity="0.5" />
        </g>

        {/* ── Right eye (animates blink) ── */}
        <g className="panda-eye-r">
          <circle cx="192" cy="143" r="21" fill="white" />
          <circle cx="192" cy="143" r="14" fill="url(#irisGrad)" />
          <circle cx="194" cy="145" r="9"  fill="#0A0A0A" />
          <circle cx="187" cy="138" r="4"  fill="white" opacity="0.9" />
          <circle cx="198" cy="150" r="2"  fill="white" opacity="0.5" />
        </g>

        {/* ── Nose ── */}
        <ellipse cx="150" cy="172" rx="13" ry="9" fill="#1C1C1C" />
        {/* Nostrils */}
        <ellipse cx="144" cy="170" rx="4.5" ry="3.2" fill="#2D2D2D" />
        <ellipse cx="156" cy="170" rx="4.5" ry="3.2" fill="#2D2D2D" />
        {/* Nose highlight */}
        <ellipse cx="147" cy="168" rx="3" ry="2" fill="rgba(255,255,255,0.3)" />

        {/* ── Mouth — gentle KFP smile ── */}
        <path
          d="M 130 188 Q 150 207 170 188"
          stroke="#1C1C1C" strokeWidth="3" fill="none"
          strokeLinecap="round"
        />
        {/* Mouth corners dimple */}
        <circle cx="130" cy="188" r="2.5" fill="#1C1C1C" />
        <circle cx="170" cy="188" r="2.5" fill="#1C1C1C" />

        {/* ── Cheek blush (subtle pink) ── */}
        <ellipse cx="84"  cy="172" rx="24" ry="15"
          fill="rgba(251,146,120,0.2)" />
        <ellipse cx="216" cy="172" rx="24" ry="15"
          fill="rgba(251,146,120,0.2)" />

        {/* ── Forehead fur tuft ── */}
        <path
          d="M 140 64 Q 150 52 160 64"
          stroke="#D0D8F0" strokeWidth="2.5" fill="none"
          strokeLinecap="round" opacity="0.7"
        />

      </g>{/* end head group */}

      {/* Ground shadow ellipse */}
      <ellipse cx="150" cy="415" rx="90" ry="10"
        fill="rgba(37,99,235,0.08)" />

    </svg>
  )
}
