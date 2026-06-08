import type React from "react";

// Boot preloader — single-pass claim-file scan.
//
// ARGOS is the letterhead of the claim file itself, not a separate wordmark
// above it. The scan line sweeps down once, citation pins land row-by-row
// as the line passes, and the loader resolves. No looping — the metaphor is
// "Argos sourced this claim, here's the work" rather than "still going."
// Skipped under prefers-reduced-motion (App.tsx sets booting=false there).

export default function Preload() {
  return (
    <div className="preload" aria-hidden="true">
      <svg
        className="pl-file"
        viewBox="0 0 200 140"
        role="img"
        aria-label="Argos claim file"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* claim file outline — centered horizontally in the viewBox */}
        <rect x="20" y="14" width="140" height="112" rx="3" className="pl-card" />

        {/* letterhead — ARGOS lives inside the file as its brand */}
        <g className="pl-letterhead">
          <rect x="28" y="21" width="7" height="7" className="pl-mk-svg" />
          <text x="40" y="27.4" className="pl-brand">ARGOS</text>
          <rect x="144" y="22" width="10" height="5" rx="1" className="pl-status" />
        </g>
        <line x1="20" y1="36" x2="160" y2="36" className="pl-rule" />

        {/* form rows — hairline label + value, hairline underline */}
        <FormRow y={50} />
        <FormRow y={72} />
        <FormRow y={94} />
        <FormRow y={116} />

        {/* scan line — sweeps top to bottom, single pass */}
        <line x1="20" y1="0" x2="160" y2="0" className="pl-scan" />

        {/* citation pins — pulse in as the scan line reaches each row, stay */}
        <CitationPin y={50} delay={0.30} />
        <CitationPin y={72} delay={0.60} />
        <CitationPin y={94} delay={0.90} />
        <CitationPin y={116} delay={1.20} />
      </svg>
    </div>
  );
}

function FormRow({ y }: { y: number }) {
  return (
    <g>
      <rect x="28" y={y - 4} width="22" height="4" rx="1" className="pl-fl" />
      <rect x="56" y={y - 4} width="60" height="4" rx="1" className="pl-fv" />
      <line x1="28" y1={y + 4} x2="152" y2={y + 4} className="pl-hair" />
    </g>
  );
}

function CitationPin({ y, delay }: { y: number; delay: number }) {
  return (
    <g
      className="pl-pin"
      style={{ animationDelay: `${delay}s` } as React.CSSProperties}
    >
      <line x1="154" y1={y} x2="166" y2={y} className="pl-pin-tick" />
      <rect x="166" y={y - 5} width="14" height="10" rx="1.5" className="pl-pin-box" />
    </g>
  );
}
