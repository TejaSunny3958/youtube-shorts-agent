import React from "react";
import "./VideoInfo.css";

export default function VideoInfo({ data }) {
  const mins = Math.floor(data.duration / 60);
  const secs = data.duration % 60;
  return (
    <div className="video-info">
      <h2 className="vi-title">{data.title}</h2>
      <div className="vi-meta">
        <span>⏱ {mins}m {secs}s</span>
        <span>✂️ {data.total_shorts} shorts generated</span>
      </div>
    </div>
  );
}
