import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import UrlForm from "./components/UrlForm";
import VideoInfo from "./components/VideoInfo";
import ShortsList from "./components/ShortsList";
import ProgressBar from "./components/ProgressBar";
import History from "./components/History";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:5000";

const POLL_MS = 1500;

export default function App() {
  const [status, setStatus]     = useState("idle"); // idle | processing | done | error
  const [taskId, setTaskId]     = useState(null);
  const [progress, setProgress] = useState(null);   // {stage, message, percent}
  const [videoData, setVideoData] = useState(null);
  const [error, setError]       = useState("");
  const [view, setView]         = useState("home"); // home | history
  const [lastUrl, setLastUrl]   = useState("");
  const pollRef = useRef(null);

  // ── Polling cleanup ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // ── Start polling when taskId changes ─────────────────────────────────────
  useEffect(() => {
    if (!taskId) return;

    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const { data } = await axios.get(
          `${API}/api/status/${taskId}`
        );

        setProgress({
          stage:   data.stage   || "processing",
          message: data.message || "Working…",
          percent: data.percent || 0,
        });

        if (data.status === "done") {
          clearInterval(pollRef.current);
          setVideoData(data.result);
          setStatus("done");
        } else if (data.status === "error") {
          clearInterval(pollRef.current);
          setError(data.error || "Processing failed.");
          setStatus("error");
        }
      } catch {
        // network blip – keep polling
      }
    }, POLL_MS);
  }, [taskId]);

  // ── Submit handler ────────────────────────────────────────────────────────
  const handleSubmit = async (url) => {
    if (pollRef.current) clearInterval(pollRef.current);
    setStatus("processing");
    setVideoData(null);
    setError("");
    setProgress({ stage: "queued", message: "Queued…", percent: 0 });
    setView("home");
    setLastUrl(url);

    try {
      const { data } = await axios.post(
        `${API}/api/process`, { url }
      );
      setTaskId(data.task_id);
    } catch (err) {
      const msg = err.response?.data?.error || err.message || "Unknown error";
      setError(msg);
      setStatus("error");
    }
  };

  // ── History load ──────────────────────────────────────────────────────────
  const handleHistoryLoad = (data) => {
    setVideoData(data);
    setStatus("done");
    setView("home");
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-row">
          <h1>🎬 YouTube Shorts Agent</h1>
          <button
            className={`history-toggle ${view === "history" ? "active" : ""}`}
            onClick={() => setView(view === "history" ? "home" : "history")}
          >
            📋 History
          </button>
        </div>
        <p>Paste a YouTube URL – the agent downloads, analyses and clips the best shorts automatically.</p>
      </header>

      <main className="app-main">
        {view === "history" ? (
          <History onLoad={handleHistoryLoad} />
        ) : (
          <>
            <UrlForm
              onSubmit={handleSubmit}
              loading={status === "processing"}
            />

            {status === "processing" && progress && (
              <ProgressBar progress={progress} />
            )}

            {status === "error" && (
              <div className="status-card error">
                <p>❌ {error}</p>
              </div>
            )}

            {status === "done" && videoData && (
              <>
                <div className="reprocess-bar">
                  <span className="reprocess-title">{videoData.title}</span>
                  <button
                    className="reprocess-btn"
                    onClick={() => handleSubmit(lastUrl)}
                    disabled={!lastUrl}
                    title="Re-run the full pipeline on this video"
                  >
                    🔄 Re-process
                  </button>
                </div>
                <VideoInfo data={videoData} />
                <ShortsList shorts={videoData.shorts} videoTitle={videoData.title} />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
