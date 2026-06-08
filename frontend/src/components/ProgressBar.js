import React from "react";
import "./ProgressBar.css";

const STAGES = [
  { key: "queued",     label: "Queue",      icon: "⏳" },
  { key: "download",   label: "Download",   icon: "⬇️" },
  { key: "transcribe", label: "Transcribe", icon: "🎙️" },
  { key: "analyze",    label: "Analyze",    icon: "🔍" },
  { key: "clip",       label: "Clip",       icon: "✂️" },
  { key: "done",       label: "Done",       icon: "✅" },
];

function stageIndex(key) {
  const idx = STAGES.findIndex((s) => s.key === key);
  return idx === -1 ? 0 : idx;
}

export default function ProgressBar({ progress }) {
  const { stage = "queued", message = "Starting…", percent = 0 } = progress || {};
  const currentIdx = stageIndex(stage);

  return (
    <div className="progress-container">
      {/* Step indicator */}
      <div className="progress-steps">
        {STAGES.map((s, i) => {
          const done    = i < currentIdx;
          const active  = i === currentIdx;
          return (
            <div
              key={s.key}
              className={`progress-step ${done ? "done" : ""} ${active ? "active" : ""}`}
            >
              <div className="step-circle">{done ? "✓" : s.icon}</div>
              <div className="step-label">{s.label}</div>
              {i < STAGES.length - 1 && (
                <div className={`step-line ${done ? "done" : ""}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>

      {/* Message */}
      <p className="progress-message">{message}</p>
    </div>
  );
}
