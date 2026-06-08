import React, { useState, useRef } from "react";
import axios from "axios";
import "./UrlForm.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:5000";

export default function UrlForm({ onSubmit, loading }) {
  const [tab, setTab] = useState("url"); // "url" | "file"
  const [url, setUrl] = useState("");
  const [file, setFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileRef = useRef();

  const handleUrlSubmit = (e) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onSubmit(trimmed);
  };

  const handleFileSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      setUploadProgress(1);
      const { data } = await axios.post(`${API}/api/upload-video`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (p) =>
          setUploadProgress(Math.round((p.loaded / p.total) * 100)),
      });
      setUploadProgress(0);
      // Reuse parent's task polling by calling onSubmit with a special sentinel
      // The parent only needs the task_id — pass it via a fake URL approach
      // Instead, we call the onSubmit handler but the parent needs task_id directly.
      // We emit the task_id wrapped in an object via a custom event to App.js
      window.dispatchEvent(new CustomEvent("localVideoTaskId", { detail: data.task_id }));
    } catch (err) {
      setUploadProgress(0);
      alert(err.response?.data?.error || err.message);
    }
  };

  return (
    <div className="url-form-wrapper">
      <div className="form-tabs">
        <button
          className={`form-tab ${tab === "url" ? "active" : ""}`}
          onClick={() => setTab("url")}
          type="button"
        >
          🔗 YouTube URL
        </button>
        <button
          className={`form-tab ${tab === "file" ? "active" : ""}`}
          onClick={() => setTab("file")}
          type="button"
        >
          📁 Upload Video
        </button>
      </div>

      {tab === "url" ? (
        <form className="url-form" onSubmit={handleUrlSubmit}>
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
      ) : (
        <form className="url-form" onSubmit={handleFileSubmit}>
          <div
            className="file-drop-zone"
            onClick={() => fileRef.current.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) setFile(f);
            }}
          >
            {file ? (
              <span className="file-name">🎬 {file.name}</span>
            ) : (
              <span className="file-placeholder">
                Click or drag a video file here<br />
                <small>MP4, MOV, AVI, MKV, WebM</small>
              </span>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="video/*"
              style={{ display: "none" }}
              onChange={(e) => setFile(e.target.files[0] || null)}
            />
          </div>
          {uploadProgress > 0 && uploadProgress < 100 && (
            <div className="upload-progress-bar">
              <div className="upload-progress-fill" style={{ width: `${uploadProgress}%` }} />
              <span>{uploadProgress}%</span>
            </div>
          )}
          <button type="submit" className="url-btn" disabled={loading || !file || uploadProgress > 0}>
            {uploadProgress > 0 ? `Uploading ${uploadProgress}%…` : loading ? "Processing…" : "Generate Shorts"}
          </button>
        </form>
      )}
    </div>
  );
}
