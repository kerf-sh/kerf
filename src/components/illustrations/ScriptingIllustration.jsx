/**
 * ScriptingIllustration — Python `kerf-sdk` snippet on the left, JSON-RPC
 * envelope arrow in the middle, the user's project files on the right.
 * Communicates "scriptable from your own machine".
 *
 * viewBox 320×200.
 */
export default function ScriptingIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Python kerf-sdk snippet sending a JSON-RPC call to a project file tree"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        KERF-SDK · PYTHON
      </text>

      {/* Python panel */}
      <rect x="20" y="44" width="156" height="134" rx="4" fill="#0f1115" stroke="#1a1d24" />
      <g fontSize="7" fontFamily="ui-monospace, monospace">
        <text x="28" y="58" fill="#5a6275">$ pip install kerf-sdk</text>
        <text x="28" y="74" fill="#ff6bd4">from</text>
        <text x="50" y="74" fill="#b8bfcc"> kerf </text>
        <text x="74" y="74" fill="#ff6bd4">import</text>
        <text x="104" y="74" fill="#b8bfcc"> Kerf</text>

        <text x="28" y="92" fill="#b8bfcc">k = Kerf.from_env()</text>

        <text x="28" y="108" fill="#5a6275"># sweep a parameter</text>
        <text x="28" y="120" fill="#6bd4ff">for</text>
        <text x="44" y="120" fill="#b8bfcc"> d </text>
        <text x="56" y="120" fill="#6bd4ff">in</text>
        <text x="68" y="120" fill="#b8bfcc"> [4, 5, 6, 8]:</text>
        <text x="34" y="132" fill="#b8bfcc">k.equations.set(</text>
        <text x="34" y="142" fill="#7BB661">    "diameter"</text>
        <text x="84" y="142" fill="#b8bfcc">, d)</text>
        <text x="34" y="152" fill="#b8bfcc">k.files.write(</text>
        <text x="34" y="162" fill="#7BB661">    "main.jscad"</text>
        <text x="34" y="172" fill="#b8bfcc">, src)</text>
      </g>

      {/* JSON-RPC envelope flying right */}
      <g transform="translate(186, 88)">
        <rect width="50" height="24" rx="3" fill="#0f1115" stroke="#ffd633" />
        <text x="25" y="10" textAnchor="middle" fontSize="6" fontFamily="ui-monospace, monospace" fill="#ffd633">
          POST /v1/rpc
        </text>
        <text x="25" y="20" textAnchor="middle" fontSize="6" fontFamily="ui-monospace, monospace" fill="#b8bfcc">
          set_equation
        </text>
      </g>

      <g stroke="#ffd633" strokeWidth="0.8" fill="none" strokeLinecap="round">
        <line x1="178" y1="100" x2="186" y2="100" />
        <line x1="236" y1="100" x2="250" y2="100" />
        <polygon points="250,100 245,97 245,103" fill="#ffd633" />
      </g>

      {/* Project files panel */}
      <rect x="248" y="44" width="60" height="134" rx="4" fill="#0f1115" stroke="#1a1d24" />
      <text x="278" y="58" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        PROJECT
      </text>
      <g fontSize="7" fontFamily="ui-monospace, monospace">
        {[
          { y: 76, name: 'main.jscad', color: '#ffe566', active: true },
          { y: 90, name: '.equations', color: '#b8bfcc' },
          { y: 104, name: 'profile.sketch', color: '#b8bfcc' },
          { y: 118, name: 'frame.assembly', color: '#b8bfcc' },
          { y: 132, name: 'sheet.drawing', color: '#b8bfcc' },
          { y: 146, name: 'board.circuit', color: '#b8bfcc' },
        ].map((f) => (
          <g key={f.name}>
            {f.active && (
              <rect x="254" y={f.y - 8} width="48" height="11" rx="2" fill="#ffd633" fillOpacity="0.10" stroke="#ffd633" strokeOpacity="0.3" />
            )}
            <text x="258" y={f.y} fill={f.color}>
              {f.name}
            </text>
          </g>
        ))}
        <text x="258" y="170" fontSize="6" fill="#7BB661">
          ↻ revisioned
        </text>
      </g>

      <text x="296" y="48" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        bring your own LLM
      </text>
    </svg>
  )
}
