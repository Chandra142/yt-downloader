from flask import Flask, request, jsonify, render_template, send_from_directory, abort, Response
import os
import re
from markupsafe import escape
from werkzeug.utils import safe_join
from config import SECRET_KEY, DOWNLOAD_DIR, DEBUG, SITE_URL
from utils import is_valid_url, check_ffmpeg, logger, normalize_url
from downloader import downloader

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY


# ---------------------------------------------------------------------------
# SEO context processor — available in all templates
# ---------------------------------------------------------------------------
@app.context_processor
def inject_seo():
    """Inject SEO variables into all templates."""
    return {
        'site_url': SITE_URL,
    }


def _seo_context(page_title, description, path, og_image=None):
    """Build a safe SEO context dict for a given page."""
    canonical = f"{SITE_URL}{path}"
    return {
        'page_title': page_title,
        'meta_description': description,
        'canonical_url': canonical,
        'og_title': page_title,
        'og_description': description,
        'og_url': canonical,
        'og_image': og_image or f"{SITE_URL}/static/img/og-default.png",
        'site_url': SITE_URL,
    }

# ---------------------------------------------------------------------------
# Security headers — added to every response
# ---------------------------------------------------------------------------
@app.after_request
def set_security_headers(response):
    """Add basic security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # CSP: allow self + Google Fonts (used in index.html)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "script-src 'self'; "
        "connect-src 'self';"
    )
    return response


# ---------------------------------------------------------------------------
# Simple in-process rate limiter (not suitable for multi-worker deployments)
# ---------------------------------------------------------------------------
import time
import threading

_rate_store: dict = {}
_rate_lock = threading.Lock()
MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '10'))


def _is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded MAX_REQUESTS_PER_MINUTE."""
    now = time.time()
    window = 60  # seconds

    with _rate_lock:
        timestamps = _rate_store.get(ip, [])
        # Keep only the timestamps within the current window
        timestamps = [t for t in timestamps if now - t < window]
        if len(timestamps) >= MAX_REQUESTS_PER_MINUTE:
            _rate_store[ip] = timestamps
            return True
        timestamps.append(now)
        _rate_store[ip] = timestamps
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    ffmpeg_available = check_ffmpeg()
    seo = _seo_context(
        'YT Downloader — Free Online Video & Audio Downloader',
        'Download videos and audio from YouTube, Vimeo, SoundCloud, Twitter/X, TikTok, and more. Supports MP4, MP3, multiple quality options, and subtitle embedding. Free, fast, and open source.',
        '/',
    )
    return render_template('index.html', ffmpeg_available=ffmpeg_available, **seo)


@app.route('/api/info', methods=['POST'])
def api_info():
    # Guard against missing / non-JSON body
    if not request.is_json:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': 'JSON body required.'}}), 400

    # Rate limiting
    client_ip = request.remote_addr or 'unknown'
    if _is_rate_limited(client_ip):
        return jsonify({
            'success': False,
            'error': {'code': 'RATE_LIMITED', 'message': 'Too many requests. Please wait a moment.'}
        }), 429

    data = request.json or {}
    url = normalize_url(str(data.get('url', '')).strip())

    # Enforce max URL length to prevent abuse
    if len(url) > 2048:
        return jsonify({'success': False, 'error': {'code': 'INVALID_URL', 'message': 'URL is too long.'}}), 400

    if not is_valid_url(url):
        return jsonify({
            'success': False,
            'error': {'code': 'INVALID_URL', 'message': 'Please enter a valid supported URL.'}
        }), 400

    info = downloader.get_video_info(url)
    if info.get('success'):
        return jsonify(info)
    return jsonify(info), 400


@app.route('/api/download', methods=['POST'])
def api_download():
    if not request.is_json:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': 'JSON body required.'}}), 400

    # Rate limiting
    client_ip = request.remote_addr or 'unknown'
    if _is_rate_limited(client_ip):
        return jsonify({
            'success': False,
            'error': {'code': 'RATE_LIMITED', 'message': 'Too many requests. Please wait a moment.'}
        }), 429

    data = request.json or {}
    url = normalize_url(str(data.get('url', '')).strip())
    format_choice = str(data.get('format', 'best')).strip()

    # Only accept choices emitted by get_video_info.  Resolution choices use
    # the ``height_<pixels>`` form and are consumed by Downloader directly.
    # Previously these valid choices were silently changed to ``best``, which
    # made the quality selector in the UI ineffective.
    allowed_formats = {'best', 'audio_only'}
    is_supported_height = re.fullmatch(r'height_(?:144|240|360|480|720|1080|1440|2160|4320)', format_choice)
    if format_choice not in allowed_formats and not is_supported_height:
        format_choice = 'best'

    if len(url) > 2048:
        return jsonify({'success': False, 'error': {'code': 'INVALID_URL', 'message': 'URL is too long.'}}), 400

    if not is_valid_url(url):
        return jsonify({
            'success': False,
            'error': {'code': 'INVALID_URL', 'message': 'Please enter a valid supported URL.'}
        }), 400

    try:
        job_id = downloader.start_download(url, format_choice)
    except Exception as e:
        err = str(e)
        if err == 'MAX_CONCURRENT_DOWNLOADS_REACHED':
            return jsonify({
                'success': False,
                'error': {'code': 'SERVER_BUSY', 'message': 'Server is busy. Please try again shortly.'}
            }), 429
        logger.error(f"Unexpected error starting download: {err}")
        return jsonify({
            'success': False,
            'error': {'code': 'INTERNAL_ERROR', 'message': 'Failed to start download.'}
        }), 500

    return jsonify({'success': True, 'job_id': job_id})


@app.route('/api/progress/<job_id>', methods=['GET'])
def api_progress(job_id):
    # Validate job_id looks like a UUID (36 chars) to reject obviously bad inputs
    if len(job_id) > 64:
        return jsonify({'success': False, 'error': {'code': 'INVALID_JOB', 'message': 'Invalid job ID.'}}), 400

    status = downloader.get_job_status(job_id)
    if not status:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_FOUND', 'message': 'Job not found or expired.'}
        }), 404

    return jsonify({
        'success': True,
        'job_id': status['job_id'],
        'status': status['status'],
        'progress': status['progress'],
        'speed': status['speed'],
        'eta': status['eta'],
        'error': status['error'],
        'filesize': status.get('filesize', ''),
        'elapsed': status.get('elapsed', ''),
        'fragment': status.get('fragment', ''),
    })


@app.route('/api/cancel/<job_id>', methods=['POST'])
def api_cancel(job_id):
    if len(job_id) > 64:
        return jsonify({'success': False, 'error': 'Invalid job ID.'}), 400

    success = downloader.cancel_job(job_id)
    if success:
        return jsonify({'success': True, 'status': 'cancelled'})
    return jsonify({'success': False, 'error': 'Job not found.'}), 404


@app.route('/api/resume/<job_id>', methods=['POST'])
def api_resume(job_id):
    if len(job_id) > 64:
        return jsonify({'success': False, 'error': {'code': 'INVALID_JOB', 'message': 'Invalid job ID.'}}), 400

    success = downloader.resume_download(job_id)
    if success:
        return jsonify({'success': True, 'job_id': job_id, 'status': 'queued'})
    return jsonify({'success': False, 'error': {'code': 'NOT_RESUMABLE', 'message': 'Cannot resume this download.'}}), 400


@app.route('/download/<job_id>', methods=['GET'])
def serve_download(job_id):
    """Serve the completed file — only the file belonging to this job."""
    if len(job_id) > 64:
        abort(400)

    status = downloader.get_job_status(job_id)
    if not status or status['status'] != 'completed' or not status.get('filename'):
        abort(404)

    filename = status['filename']

    # Extra safety: reject filenames containing path separators
    if os.sep in filename or ('/' in filename) or ('\\' in filename):
        logger.warning(f"Suspicious filename blocked for job {job_id}: {filename}")
        abort(400)

    # safe_join will raise NotFound if the path escapes DOWNLOAD_DIR
    safe_path = safe_join(str(DOWNLOAD_DIR), filename)
    if not safe_path or not os.path.isfile(safe_path):
        abort(404)

    return send_from_directory(
        str(DOWNLOAD_DIR),
        filename,
        as_attachment=True,
    )


# ---------------------------------------------------------------------------
# SEO routes — robots.txt, sitemap.xml, landing pages
# ---------------------------------------------------------------------------

@app.route('/robots.txt')
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /download/\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    return Response(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    pages = [
        ('/', '1.0', 'daily'),
        ('/youtube-video-downloader', '0.8', 'weekly'),
        ('/youtube-audio-downloader', '0.8', 'weekly'),
    ]
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc_path, priority, changefreq in pages:
        xml_parts.append('  <url>')
        xml_parts.append(f'    <loc>{SITE_URL}{loc_path}</loc>')
        xml_parts.append(f'    <changefreq>{changefreq}</changefreq>')
        xml_parts.append(f'    <priority>{priority}</priority>')
        xml_parts.append('  </url>')
    xml_parts.append('</urlset>')
    xml_body = '\n'.join(xml_parts)
    return Response(xml_body, mimetype='application/xml')


@app.route('/youtube-video-downloader')
def youtube_video_downloader():
    ffmpeg_available = check_ffmpeg()
    seo = _seo_context(
        'YouTube Video Downloader — Download YouTube Videos as MP4',
        'Download YouTube videos in MP4 format. Choose from multiple quality options including 1080p, 720p, 480p, and 360p. Free, fast, and no registration required.',
        '/youtube-video-downloader',
    )
    return render_template('landing_video.html', ffmpeg_available=ffmpeg_available, **seo)


@app.route('/youtube-audio-downloader')
def youtube_audio_downloader():
    ffmpeg_available = check_ffmpeg()
    seo = _seo_context(
        'YouTube Audio Downloader — Convert YouTube to MP3',
        'Extract audio from YouTube videos and download as MP3. High quality 192kbps audio conversion. Free, fast, and no registration required.',
        '/youtube-audio-downloader',
    )
    return render_template('landing_audio.html', ffmpeg_available=ffmpeg_available, **seo)


# ---------------------------------------------------------------------------
# Custom error pages — never expose Python tracebacks
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.', noindex=True), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}")
    return render_template('error.html', code=500, message='Internal server error.', noindex=True), 500


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=DEBUG, port=5000)
