# 🎬 YouTube Shorts Agent

An AI-powered pipeline that takes any YouTube video URL and automatically produces up to 9 ready-to-post vertical short clips — complete with visual effects, burned-in captions, and optional background music.

---

## Business Purpose

Long-form YouTube videos (tutorials, podcasts, vlogs, interviews) contain dozens of viral-worthy moments that most creators never clip. Doing it manually means:

- Watching the full video to find good moments
- Trimming, resizing to 9:16 portrait, adding captions and effects — one at a time
- Repeating for every video

This agent removes all of that. Paste a URL → get 9 polished Shorts in ~30 seconds.

**Target users:** YouTube creators, social media managers, content repurposing agencies.

**Revenue angle:** Offer as a SaaS tool — creators pay per video processed or on a monthly subscription.

---

## How the Pipeline Works

```
YouTube URL
    │
    ▼
1. DOWNLOAD          yt-dlp → forces 720p H.264 MP4
    │                Chrome cookies bypass bot-detection
    │                Result cached — same URL never re-downloaded
    ▼
2. TRANSCRIBE        faster-whisper (base model, CPU, int8)
    │                Converts audio → timestamped word segments
    │                Transcript JSON cached after first run
    │                Progress streamed live to the UI (0–33%)
    ▼
3. ANALYSE           Two strategies run in order:
    │
    ├─ Gemini 2.5 Flash (primary)
    │      Receives full transcript + video title + duration
    │      Asked to pick 9 most engaging 30-second windows
    │      Returns JSON: [{ start, end, label, score }]
    │      Scores by: hooks, emotional peaks, standalone value
    │
    └─ Rule-Based Fallback (if Gemini returns 0 segments)
           Strategy A – Chapter markers (if the video has them)
           Strategy B – Sliding 30s window across full video
             - Scores each window by keyword density:
               "tip", "trick", "hack", "secret", "how to", etc.
             - Always includes Opening Hook (0–30s) and Closing CTA
             - Deduplicates overlapping windows (>50% overlap removed)
    │
    ▼
4. GENERATE TITLES   Gemini 2.5 Flash (second call)
    │                For each selected segment it writes one
    │                punchy viral title (max 60 chars, no hashtags)
    │                e.g. "The Trick Nobody Tells You About"
    ▼
5. CLIP + EFFECTS    FFmpeg (via imageio-ffmpeg bundled binary)
    │
    ├─ Resize: scale to 1080×1920 (9:16 portrait)
    │          letterbox/pillarbox with black bars — no cropping
    │
    ├─ Visual effect: one of 7 colour grades rotated across clips
    │     ❄️ Cinematic Cold  🔥 Warm Glow   🎨 Color Pop
    │     🌃 Neon Dark       🎞️ Film Grain  ✨ Golden Hour  🌊 Moody Blue
    │
    ├─ Captions: Whisper segments burned in as .ASS subtitles
    │
    └─ Music: background lofi track mixed at 15% volume (optional)
    │
    ▼
6. SERVE RESULTS     Flask API returns clip URLs to React frontend
                     Each clip card shows:
                       - Inline video preview
                       - AI-generated title
                       - 🤖 Gemini badge (if AI-selected)
                       - ⭐ Best Short badge (rank #1)
                       - ⬇ Download button
                       - 🎵 Add Music / 🔇 Remove Music toggle
                             + volume slider (5–50%)
                       - ▲ Upload to YouTube button
```

---

## Video Segmentation — Deep Dive

### Why 30 seconds?
YouTube Shorts max length is 60s, but 30s is the sweet spot for completion rate and algorithmic boost.

### Gemini strategy (primary)
The transcript is formatted as:
```
[12.5s] And here's the part nobody talks about
[15.1s] If you do this one thing every morning...
```
Gemini is prompted to find windows where the speaker delivers **self-contained value** — a surprising fact, a strong hook, an emotional peak — without needing surrounding context. It returns start/end timestamps directly.

### Rule-based strategy (fallback)
When Gemini fails or the transcript is empty:

1. **Chapters** — if the video has chapter markers and a chapter is 15–30s, it becomes a clip directly. Longer chapters are sliced into 30s sub-clips.

2. **Sliding window** — a 30-second window slides across the video in 30-second steps. Each window is scored:
   - **+1.0** per hook keyword found in the video description at that timestamp position
   - **+1.5** per hook keyword found in the spoken words (Whisper transcript) within that window
   - **+5.0** bonus for the opening 30s (Opening Hook)
   - **+4.0** bonus for the closing 30s (Closing CTA)
   - Windows with >50% time overlap with a higher-scoring window are dropped

Top 9 unique windows by score are kept.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3 + Flask 3.1.3 |
| AI — segment selection | Google Gemini 2.5 Flash |
| AI — transcription | faster-whisper (CTranslate2, CPU int8) |
| Video download | yt-dlp (Chrome cookie auth) |
| Video processing | FFmpeg via imageio-ffmpeg |
| Database | SQLite (history) |
| Frontend | React 18 + react-scripts |
| Styling | Plain CSS (dark theme) |

---

## Project Structure

```
Shorts/
├── backend/
│   ├── app.py                  # Flask API — all routes
│   ├── db.py                   # SQLite history
│   ├── .env                    # GOOGLE_API_KEY
│   ├── assets/music/           # Background music files (.mp3)
│   ├── outputs/
│   │   ├── downloads/          # Cached MP4s + transcripts + meta
│   │   └── shorts/             # Output clips
│   └── processors/
│       ├── downloader.py       # yt-dlp wrapper + metadata cache
│       ├── transcriber.py      # faster-whisper + ASS subtitle writer
│       ├── analyzer.py         # Rule-based segment selector
│       ├── gemini_analyzer.py  # Gemini AI segment selector + title gen
│       ├── clipper.py          # FFmpeg clip + resize + captions + music
│       ├── effects.py          # 7 colour-grade filter chains
│       └── uploader.py         # YouTube Data API v3 upload
└── frontend/
    └── src/
        ├── App.js              # Root — polling, state, re-process button
        └── components/
            ├── UrlForm.js      # URL input
            ├── ProgressBar.js  # Live stage + percent bar
            ├── VideoInfo.js    # Title / duration / stats
            ├── ShortsList.js   # Clip cards + music toggle + upload
            └── History.js      # Past processed videos
```

---

## Running Locally

```bash
# Backend
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Install PyTorch CPU first (small ~200MB build, not the 2GB GPU version)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install all other dependencies
pip install -r requirements.txt

# Create your .env file
copy .env.example .env
# → Edit .env and add your GOOGLE_API_KEY

python app.py        # → http://localhost:5000

# Frontend (in a separate terminal)
cd frontend
npm install
npm start            # → http://localhost:3000
```
