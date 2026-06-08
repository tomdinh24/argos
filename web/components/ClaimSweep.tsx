import type React from "react";

// Hero animation for the landing left pane.
//
// Visual metaphor for Argos: a stack of claim files (the file room), a scan
// line sweeping down the active file (triage / sourcing pass), and citation
// pins lighting up as evidence is anchored to documents. Pure SVG + CSS, no
// canvas, no WebGL — stays in the deep-tech register and respects
// prefers-reduced-motion (the sweep stops, the pins still show).

export default function ClaimSweep() {
  return (
    <svg
      className="csweep"
      viewBox="0 0 420 340"
      role="img"
      aria-label="Argos sources evidence and pins citations across a claim file."
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        {/* monospaced caption font — inherits from the page */}
        <style>{`
          .csweep text { font-family: var(--mono); fill: var(--muted); }
        `}</style>
      </defs>

      {/* back files (depth) */}
      <g className="csweep-stack">
        <rect x="58" y="60" width="320" height="240" rx="3" className="csweep-card csweep-back" />
        <rect x="48" y="50" width="320" height="240" rx="3" className="csweep-card csweep-mid" />
      </g>

      {/* active claim file — the one being sourced */}
      <g className="csweep-active">
        <rect x="38" y="40" width="320" height="240" rx="3" className="csweep-card csweep-front" />

        {/* file header — claim id, status */}
        <text x="52" y="62" className="csweep-id">CLM-1042</text>
        <text x="346" y="62" className="csweep-status" textAnchor="end">OPEN</text>
        <line x1="38" y1="74" x2="358" y2="74" className="csweep-rule" />

        {/* form rows — hairline fields with placeholder text */}
        <g className="csweep-rows">
          <FormRow y={92} label="INSURED" value="NORTHBRIDGE LOGISTICS" />
          <FormRow y={114} label="POLICY" value="POL-2026-0093" />
          <FormRow y={136} label="LOSS" value="REAR-END / SIGNALED INT." />
          <FormRow y={158} label="JURIS" value="CA" />
          <FormRow y={180} label="SPECIALS" value="$84,120" />
          <FormRow y={202} label="MULT" value="2.1 · TIER B" />
          <FormRow y={224} label="DEFENSE" value="+$11,000 PHASE-ALIGNED" />
          <FormRow y={246} label="RESERVE" value="$92,000" />
        </g>

        {/* sweep line — moves vertically across the file */}
        <line x1="38" y1="0" x2="358" y2="0" className="csweep-line" />

        {/* citation pins — each anchors to a field, fades in as the sweep passes */}
        <CitationPin x={360} y={90} delay={0} label="01" />
        <CitationPin x={360} y={134} delay={0.8} label="02" />
        <CitationPin x={360} y={178} delay={1.6} label="03" />
        <CitationPin x={360} y={222} delay={2.4} label="04" />
      </g>

      {/* baseline mono telemetry — spans full content width so it bookends the card + pins */}
      <text x="38" y="320" className="csweep-tele">SOURCING · 04 CITATIONS · 0.7s</text>
      <text x="382" y="320" className="csweep-tele" textAnchor="end">v0</text>
    </svg>
  );
}

function FormRow({ y, label, value }: { y: number; label: string; value: string }) {
  return (
    <g>
      <text x="52" y={y} className="csweep-fl">{label}</text>
      <text x="120" y={y} className="csweep-fv">{value}</text>
      <line x1="52" y1={y + 4} x2="344" y2={y + 4} className="csweep-hair" />
    </g>
  );
}

function CitationPin({ x, y, delay, label }: { x: number; y: number; delay: number; label: string }) {
  return (
    <g
      className="csweep-pin"
      style={{ ["--pin-delay" as string]: `${delay}s` } as React.CSSProperties}
    >
      <line x1={x - 16} y1={y - 4} x2={x} y2={y - 4} className="csweep-pin-tick" />
      <rect x={x} y={y - 12} width="22" height="14" rx="2" className="csweep-pin-box" />
      <text x={x + 11} y={y - 2} className="csweep-pin-label" textAnchor="middle">{label}</text>
    </g>
  );
}
