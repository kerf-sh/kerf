/**
 * GitIllustration — git-graph metaphor on the left + clean GitHub sync tile
 * on the right. Lane labels sit ABOVE each lane (not on the commit line)
 * so they never overlap the graph; GitHub mark uses the canonical octocat
 * silhouette path scaled to the tile.
 *
 * viewBox 320×200. Palette locked.
 */
export default function GitIllustration({ className = '' }) {
  const MAIN = '#ffd633'
  const FEAT_A = '#6bd4ff'
  const FEAT_B = '#ff6bd4'

  const LANE_MAIN_Y = 116
  const LANE_A_Y = 82
  const LANE_B_Y = 150

  // Commit x positions along main lane. Left margin starts at x=42 so lane
  // labels (right-anchored at x=38) sit in their own 16px gutter before the
  // first commit, never touching the graph.
  const X = [44, 72, 100, 128, 156, 184]

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="A horizontal git graph with a feature branch diverging from and merging back into main, plus a second feature branch in progress, syncing to GitHub"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header */}
      <text
        x="22"
        y="32"
        fontSize="9"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill="#6a7185"
        letterSpacing="1.4"
      >
        GIT · CLOUD SYNC
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === branch curves === */}
      <g fill="none" strokeWidth="1.6" strokeLinecap="round">
        <line x1={X[0]} y1={LANE_MAIN_Y} x2={X[5]} y2={LANE_MAIN_Y} stroke={MAIN} />

        {/* feat/a: branch from main at X[1], merge back at X[4] */}
        <path
          d={`M ${X[1]} ${LANE_MAIN_Y} C ${X[1] + 10} ${LANE_MAIN_Y}, ${X[2] - 10} ${LANE_A_Y}, ${X[2]} ${LANE_A_Y}`}
          stroke={FEAT_A}
        />
        <line x1={X[2]} y1={LANE_A_Y} x2={X[3]} y2={LANE_A_Y} stroke={FEAT_A} />
        <path
          d={`M ${X[3]} ${LANE_A_Y} C ${X[3] + 10} ${LANE_A_Y}, ${X[4] - 10} ${LANE_MAIN_Y}, ${X[4]} ${LANE_MAIN_Y}`}
          stroke={FEAT_A}
        />

        {/* feat/b: branch from main at X[3], in-progress tip */}
        <path
          d={`M ${X[3]} ${LANE_MAIN_Y} C ${X[3] + 10} ${LANE_MAIN_Y}, ${X[4] - 10} ${LANE_B_Y}, ${X[4]} ${LANE_B_Y}`}
          stroke={FEAT_B}
        />
        <line x1={X[4]} y1={LANE_B_Y} x2={X[5] - 4} y2={LANE_B_Y} stroke={FEAT_B} />
      </g>

      {/* lane labels sit ABOVE each lane so they never overlap the graph line.
          Each label is offset 10px above its lane.  Labels are minimal and
          right-aligned to x=38 to leave a clear 6px gutter before X[0]=44. */}
      <g
        fontSize="7"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        textAnchor="end"
      >
        <text x="38" y={LANE_A_Y - 7} fill={FEAT_A} opacity="0.9">feat/a</text>
        <text x="38" y={LANE_MAIN_Y - 7} fill={MAIN}>main</text>
        <text x="38" y={LANE_B_Y - 7} fill={FEAT_B} opacity="0.9">feat/b</text>
      </g>

      {/* === commit dots === */}
      <CommitDot cx={X[0]} cy={LANE_MAIN_Y} color={MAIN} />
      <CommitDot cx={X[1]} cy={LANE_MAIN_Y} color={MAIN} />
      <CommitDot cx={X[3]} cy={LANE_MAIN_Y} color={MAIN} />
      <CommitDot cx={X[4]} cy={LANE_MAIN_Y} color={MAIN} merge />
      <CommitDot cx={X[5]} cy={LANE_MAIN_Y} color={MAIN} head />

      <CommitDot cx={X[2]} cy={LANE_A_Y} color={FEAT_A} />
      <CommitDot cx={X[3]} cy={LANE_A_Y} color={FEAT_A} />

      <CommitDot cx={X[4]} cy={LANE_B_Y} color={FEAT_B} />
      <CommitDot cx={X[5] - 4} cy={LANE_B_Y} color={FEAT_B} tip />

      {/* HEAD chip below the latest main commit */}
      <g transform={`translate(${X[5] - 16}, ${LANE_MAIN_Y + 12})`}>
        <rect width="34" height="13" rx="2.5" fill="#0a0b0d" stroke={MAIN} strokeOpacity="0.75" />
        <text
          x="17"
          y="9.5"
          textAnchor="middle"
          fontSize="7"
          fontFamily="ui-monospace, SFMono-Regular, monospace"
          fill={MAIN}
        >
          HEAD
        </text>
      </g>

      {/* === GitHub sync tile (right side) ===
          Uses the canonical GitHub Mark path (24×24 source) scaled to 30×30
          so it reads clearly as the GitHub logo. */}
      <g transform="translate(228, 64)">
        <rect width="70" height="56" rx="6" fill="#0f1115" stroke="#1a1d24" />
        <g transform="translate(8, 8) scale(1.25)">
          <path
            d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"
            fill="#cbd0dc"
          />
        </g>
        {/* GitHub label + sync status */}
        <text
          x="64"
          y="22"
          textAnchor="end"
          fontSize="9"
          fontFamily="ui-sans-serif, system-ui, sans-serif"
          fontWeight="600"
          fill="#cbd0dc"
        >
          GitHub
        </text>
        <text
          x="64"
          y="36"
          textAnchor="end"
          fontSize="7"
          fontFamily="ui-monospace, SFMono-Regular, monospace"
          fill="#7BB661"
        >
          ↑ in sync
        </text>
      </g>

      {/* sync arrow from latest commit → tile (dashed) */}
      <g stroke="#3a4150" strokeWidth="0.8" fill="none" strokeDasharray="2 2">
        <path d={`M ${X[5] + 4} ${LANE_MAIN_Y - 4} Q 210 96 228 92`} />
      </g>

      {/* footer */}
      <text
        x="22"
        y="178"
        fontSize="7"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill="#5a6275"
      >
        pygit2 · branches · merges · push / pull
      </text>
    </svg>
  )
}

function CommitDot({ cx, cy, color, head, merge, tip }) {
  const outerR = head ? 5.5 : merge ? 5 : 4
  return (
    <g>
      {tip && (
        <circle
          cx={cx}
          cy={cy}
          r={outerR + 3}
          fill="none"
          stroke={color}
          strokeOpacity="0.35"
          strokeWidth="0.8"
        />
      )}
      <circle cx={cx} cy={cy} r={outerR} fill="#0a0b0d" stroke={color} strokeWidth="1.4" />
      <circle cx={cx} cy={cy} r={outerR - 2.2} fill={color} />
    </g>
  )
}
