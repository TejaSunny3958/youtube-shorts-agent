import React, { useEffect, useState } from "react";
import axios from "axios";
import "./History.css";

function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s}s`;
}

function formatDate(iso) {
  try {
    return new Date(iso + "Z").toLocaleString();
  } catch {
    return iso;
  }
}

export default function History({ onLoad }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingId, setLoadingId] = useState(null);

  useEffect(() => {
    axios
      .get("http://localhost:5000/api/history")
      .then((r) => setItems(r.data))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  async function handleLoad(videoId) {
    setLoadingId(videoId);
    try {
      const r = await axios.get(
        `http://localhost:5000/api/history/${videoId}`
      );
      onLoad(r.data);
    } catch {
      alert("Could not load this video's shorts.");
    } finally {
      setLoadingId(null);
    }
  }

  if (loading) {
    return <p className="history-empty">Loading history…</p>;
  }

  if (!items.length) {
    return (
      <p className="history-empty">
        No history yet. Process a YouTube URL to get started.
      </p>
    );
  }

  return (
    <div className="history-panel">
      <h2 className="history-title">📋 Processing History</h2>
      <ul className="history-list">
        {items.map((v) => (
          <li key={v.video_id} className="history-item">
            <div className="history-info">
              <span className="history-video-title">{v.title}</span>
              <span className="history-meta">
                {formatDuration(v.duration)} · {v.total_shorts} shorts ·{" "}
                {formatDate(v.created_at)}
              </span>
            </div>
            <button
              className="history-load-btn"
              disabled={loadingId === v.video_id}
              onClick={() => handleLoad(v.video_id)}
            >
              {loadingId === v.video_id ? "Loading…" : "Load"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
