import React, { useState } from "react";
import axios from "axios";
import "./ShortsList.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:5000";

const EFFECT_LABELS = {
  cinematic_cold: "❄️ Cinematic Cold",
  warm_glow:      "🔥 Warm Glow",
  color_pop:      "🎨 Color Pop",
  neon_dark:      "🌃 Neon Dark",
  film_grain:     "🎞️ Film Grain",
  golden_hour:    "✨ Golden Hour",
  moody_blue:     "🌊 Moody Blue",
  none:           "📹 Raw",
};

function UploadButton({ s, videoTitle }) {
  const [state, setState] = useState("idle"); // idle | checking | uploading | done | error
  const [ytUrl, setYtUrl]   = useState("");
  const [errMsg, setErrMsg] = useState("");

  const shortTitle = `${videoTitle || "Short"} – ${s.label} #Shorts`.slice(0, 100);

  async function handleUpload() {
    setState("checking");
    setErrMsg("");
    try {
      // Check if we're already authenticated
      const authCheck = await axios.get(
        `${API}/api/youtube/auth` {
        // Need to auth first
        window.open(authCheck.data.auth_url, "_blank");
        setErrMsg("Opened YouTube login in a new tab. Re-click Upload after authorising.");
        setState("idle");
        return;
      }
    } catch (err) {
      if (err.response?.status === 503) {
        setErrMsg(err.response.data.error);
        setState("error");
        return;
      }
      // 200 without auth_url means already authed – continue
    }

    setState("uploading");
    try {
      const { data } = await axios.post(
        `${API}/api/youtube/upload`,
        { clip_file: s.clip_file, title: shortTitle }
      );
      setYtUrl(data.url);
      setState("done");
    } catch (err) {
      if (err.response?.status === 401) {
        // Not authenticated
        try {
          const { data } = await axios.get(
            `${API}/api/youtube/auth`
          );
          if (data.auth_url) {
            window.open(data.auth_url, "_blank");
            setErrMsg("Opened YouTube login. Re-click Upload after authorising.");
          }
        } catch {}
        setState("idle");
      } else {
        setErrMsg(err.response?.data?.error || err.message);
        setState("error");
      }
    }
  }

  if (state === "done") {
    return (
      <a
        className="yt-upload-btn done"
        href={ytUrl}
        target="_blank"
        rel="noreferrer"
      >
        ▶ View on YouTube
      </a>
    );
  }

  return (
    <div className="yt-upload-wrapper">
      <button
        className={`yt-upload-btn ${state}`}
        disabled={state === "checking" || state === "uploading"}
        onClick={handleUpload}
      >
        {state === "uploading" ? "Uploading…"
         : state === "checking" ? "Checking auth…"
         : "▲ Upload to YouTube"}
      </button>
      {errMsg && <p className="yt-upload-error">{errMsg}</p>}
    </div>
  );
}

function MusicToggle({ s, onRemixed }) {
  const [state, setState] = useState("idle"); // idle | working | error
  const [errMsg, setErrMsg] = useState("");
  const [hasMusic, setHasMusic] = useState(s.has_music);
  const [volume, setVolume] = useState(15); // 0-100

  async function toggle() {
    setState("working");
    setErrMsg("");
    try {
      const { data } = await axios.post(`${API}/api/remix`, {
        clip_file: s.clip_file,
        add_music: !hasMusic,
        music_volume: volume / 100,
      });
      setHasMusic(!hasMusic);
      setState("idle");
      onRemixed(data);
    } catch (err) {
      setErrMsg(err.response?.data?.error || err.message);
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  }

  return (
    <div className="music-toggle-wrapper">
      <button
        className={`music-toggle-btn ${hasMusic ? "on" : "off"} ${state}`}
        onClick={toggle}
        disabled={state === "working"}
        title={hasMusic ? "Remove background music" : "Add background music"}
      >
        {state === "working" ? "⏳ Processing…" : hasMusic ? "🔇 Remove Music" : "🎵 Add Music"}
      </button>
      {hasMusic && (
        <div className="music-volume-row">
          <span className="volume-label">🔊</span>
          <input
            type="range" min="5" max="50" step="5"
            value={volume}
            onChange={e => setVolume(Number(e.target.value))}
            className="volume-slider"
            title={`Music volume: ${volume}%`}
          />
          <span className="volume-pct">{volume}%</span>
        </div>
      )}
      {errMsg && <p className="yt-upload-error">{errMsg}</p>}
    </div>
  );
}

function ShortCard({ s, videoTitle }) {
  const [clipData, setClipData] = useState(s);

  const videoUrl = clipData.download_url
    ? `${API}${clipData.download_url}`
    : null;

  function handleRemixed(newData, addedMusic) {
    setClipData(prev => ({
      ...prev,
      clip_file: newData.clip_file,
      download_url: newData.download_url,
      has_music: addedMusic,
    }));
  }

  return (
    <div className={`short-card ${s.is_best ? "best" : ""}`}>
      {s.is_best && <div className="best-badge">⭐ Best Short</div>}

      {videoUrl && (
        <div className="video-wrapper">
          <div className="effect-badge">
            {EFFECT_LABELS[s.effect] || "📹 " + (s.effect || "Raw")}
          </div>
          <video
            className="short-video"
            src={videoUrl}
            controls
            playsInline
            preload="metadata"
          />
        </div>
      )}

      <div className="short-info">
        <div className="short-header">
          <span className="short-rank">#{s.rank}</span>
          <span className="short-label">{s.label}</span>
        </div>
        {s.ai_title && (
          <div className="short-ai-title">
            <span className="ai-icon">✦</span> {s.ai_title}
          </div>
        )}
        <div className="short-meta">
          <span>⏱ {s.duration}s</span>
          {clipData.has_music && <span>🎵 Music</span>}
          {s.has_captions && <span>💬 Captions</span>}
          {s.source === "gemini" && <span className="gemini-tag">🤖 Gemini</span>}
        </div>
        <div className="short-actions">
          {videoUrl && (
            <a className="short-download" href={videoUrl} download={clipData.clip_file}>
              ⬇ Download
            </a>
          )}
          <MusicToggle s={clipData} onRemixed={(d) => handleRemixed(d, !clipData.has_music)} />
          {clipData.clip_file && (
            <UploadButton s={clipData} videoTitle={videoTitle} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function ShortsList({ shorts, videoTitle }) {
  return (
    <div className="shorts-section">
      <h2 className="shorts-heading">Generated Shorts ({shorts.length})</h2>
      <div className="shorts-grid">
        {shorts.map((s) => (
          <ShortCard key={s.rank} s={s} videoTitle={videoTitle} />
        ))}
      </div>
    </div>
  );
}

