/**
 * GitIllustration — multi-lane lattice graph (main + 2 feature branches)
 * with a GitHub sync glyph in the corner. Communicates "real git +
 * cloud sync" for the cloud tier.
 *
 * viewBox 320×200.
 */
function Dot({ cx, cy, color, label, refLabel }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r="4.5" fill="#0a0b0d" stroke={color} strokeWidth="1.4" />
      <circle cx={cx} cy={cy} r="1.8" fill={color} />
      <text
        x={cx + 12}
        y={cy + 3}
        fontSize="7.5"
        fontFamily="ui-monospace, monospace"
        fill="#b8bfcc"
      >
        {label}
      </text>
      {refLabel && (
        <text
          x={cx + 12}
          y={cy + 12}
          fontSize="6.5"
          fontFamily="ui-monospace, monospace"
          fill={color}
        >
          {refLabel}
        </text>
      )}
    </g>
  )
}

export default function GitIllustration({ className = '' }) {
  // Three lanes at x = 60 (main), 110 (feat-a), 160 (feat-b).
  const main = '#ffd633'
  const lane2 = '#6bd4ff'
  const lane3 = '#ff6bd4'

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Multi-lane git graph with three branches and a GitHub sync indicator"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        GIT · CLOUD SYNC
      </text>

      {/* lattice lines */}
      <g fill="none" strokeWidth="1.4" strokeLinecap="round">
        {/* main lane (vertical) */}
        <line x1="60" y1="48" x2="60" y2="172" stroke={main} />
        {/* feat-a branch out from main */}
        <path d="M 60 76 C 60 90, 110 90, 110 104" stroke={lane2} />
        <line x1="110" y1="104" x2="110" y2="148" stroke={lane2} />
        {/* feat-a merges back to main */}
        <path d="M 110 148 C 110 160, 60 160, 60 172" stroke={lane2} />
        {/* feat-b branch out from main (later) */}
        <path d="M 60 124 C 60 134, 160 134, 160 144" stroke={lane3} />
        <line x1="160" y1="144" x2="160" y2="168" stroke={lane3} />
      </g>

      {/* commit dots */}
      <Dot cx={60} cy={56} color={main} label="initial scaffold" />
      <Dot cx={60} cy={80} color={main} label="add bracket part" />
      <Dot cx={110} cy={108} color={lane2} label="wip: fillet" refLabel="feat/fillet" />
      <Dot cx={110} cy={132} color={lane2} label="fillet ok" />
      <Dot cx={60} cy={128} color={main} label="merge fillet" />
      <Dot cx={160} cy={152} color={lane3} label="board v2" refLabel="feat/pcb" />
      <Dot cx={60} cy={168} color={main} label="release v0.4" refLabel="HEAD → main" />

      {/* GitHub sync glyph */}
      <g transform="translate(244, 50)">
        <rect width="56" height="44" rx="6" fill="#0f1115" stroke="#1a1d24" />
        <g transform="translate(8, 8)">
          {/* Octocat-ish silhouette */}
          <circle cx="10" cy="10" r="8" fill="#1a1d24" stroke="#b8bfcc" strokeWidth="0.8" />
          <path
            d="M 10 4 C 13 4, 15 6, 15 9 L 15 11 C 15 13, 13 14, 11 14 L 11 16 L 9 16 L 9 14 C 7 14, 5 13, 5 11 L 5 9 C 5 6, 7 4, 10 4 Z"
            fill="#b8bfcc"
          />
          <text x="22" y="12" fontSize="7" fontFamily="ui-monospace, monospace" fill="#b8bfcc">
            github
          </text>
          <text x="22" y="22" fontSize="6" fontFamily="ui-monospace, monospace" fill="#7BB661">
            ↑ in sync
          </text>
        </g>
      </g>

      {/* footer */}
      <text x="22" y="184" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        go-git · pygit2 · S3 storer
      </text>
      <text x="296" y="184" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        AES-GCM tokens
      </text>
    </svg>
  )
}
