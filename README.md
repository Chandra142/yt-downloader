# YT Downloader

Free online video and audio downloader built with Flask, yt-dlp, and FFmpeg.

**[Live Demo](https://yt-downloader-6exo.onrender.com)**

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, Flask, Gunicorn |
| Frontend | HTML5, CSS3, Vanilla JS |
| Download engine | yt-dlp + FFmpeg |
| Deployment | Docker on Render |

## Features

- Download videos as MP4 in multiple quality options
- Extract audio as MP3 (192 kbps)
- Subtitle embedding (English, auto-generated)
- Metadata preview (title, channel, duration, thumbnail)
- Real-time progress with speed and ETA
- Dark/light mode toggle
- Paste from clipboard and keyboard shortcuts
- Rate limiting and concurrent download caps
- Full SEO setup (robots.txt, sitemap, landing pages, JSON-LD)

## Quick Start

### Prerequisites

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/download.html) installed and on your PATH

### Setup

```bash
# Clone
git clone https://github.com/your-username/yt-downloader.git
cd yt-downloader

# Virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Install FFmpeg (Windows)

1. Download from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin` to your system `PATH`
4. Verify: `ffmpeg -version`

## Configuration

Copy `.env.example` to `.env` and edit as needed. Never commit `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-...` | Flask session secret |
| `DOWNLOAD_DIR` | `downloads` | Temp download directory |
| `MAX_CONCURRENT_DOWNLOADS` | `5` | Max simultaneous downloads |
| `JOB_EXPIRATION` | `3600` | Seconds before job cleanup |
| `FLASK_ENV` | `development` | `production` or `development` |
| `MAX_REQUESTS_PER_MINUTE` | `10` | Per-IP rate limit |
| `SITE_URL` | `http://127.0.0.1:5000` | Public URL for SEO tags |

## Project Structure

```
yt-downloader/
├── app.py                  Flask routes + SEO
├── downloader.py           yt-dlp wrapper + job manager
├── config.py               Environment config
├── utils.py                URL validation, helpers
├── templates/              HTML templates
│   ├── index.html          Homepage
│   ├── error.html          Error page (noindex)
│   ├── landing_video.html  YouTube video landing
│   └── landing_audio.html  YouTube audio landing
├── static/
│   ├── css/style.css
│   └── js/app.js
├── tests/
│   ├── test_routes.py
│   ├── test_utils.py
│   └── test_seo.py
├── Dockerfile
├── render.yaml
├── requirements.txt
└── LICENSE
```

## Development

### Run tests

```bash
pytest -v
```

109 tests covering routes, utils, and SEO. No real network requests.

### Run locally

```bash
python app.py
```

### Production (Gunicorn)

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
```

## Deployment

1. Push to GitHub
2. Go to [render.com](https://render.com) > New > Web Service
3. Connect your repo — Render detects `render.yaml` automatically
4. Click Deploy

## Architecture

```
Browser -> Flask (app.py)
  |   /api/info         Metadata extraction
  |   /api/download     Start background download
  |   /api/progress     Poll job status
  |   /api/cancel       Cancel a job
  |
  +-- utils.py          URL validation, sanitization
  +-- config.py         Environment variables
  +-- downloader.py     yt-dlp + threading + in-memory jobs
         -> downloads/
```

## Security

- Backend URL validation (frontend input not trusted)
- Format whitelist (`best`, `audio_only`, `height_*` only)
- Path traversal protection (`werkzeug.safe_join`)
- Security headers (CSP, X-Frame-Options, nosniff)
- Per-IP rate limiting
- No shell injection (Python API, never `shell=True`)
- No secrets or stack traces in responses

## SEO

- `robots.txt` with sitemap reference
- `sitemap.xml` listing all public pages
- Landing pages: `/youtube-video-downloader`, `/youtube-audio-downloader`
- JSON-LD structured data on all public pages
- Open Graph and Twitter Card meta tags
- `noindex` on error pages

Set `SITE_URL` to your production domain for correct canonical URLs.

## Limitations

- **In-memory state** — job progress lost on restart
- **Ephemeral storage** — files deleted on container restart (by design on cloud platforms)
- **Single-process rate limiter** — does not span multiple Gunicorn workers
- **YouTube on cloud** — YouTube blocks requests from datacenter IPs; non-YouTube platforms work reliably

## License

[MIT](LICENSE)
