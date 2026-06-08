import React, { useState } from "react";
import "./UrlForm.css";

export default function UrlForm({ onSubmit, loading }) {
  const [url, setUrl] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onSubmit(trimmed);
  };

  return (
    <form className="url-form" onSubmit={handleSubmit}>
      <input
        type="url"
        className="url-input"
        placeholder="https://www.youtube.com/watch?v=..."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={loading}
        required
      />
      <button type="submit" className="url-btn" disabled={loading || !url.trim()}>
        {loading ? "Processing…" : "Generate Shorts"}
      </button>
    </form>
  );
}
