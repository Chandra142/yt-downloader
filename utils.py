import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import shutil
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ytdownloader')

DIRECT_FILE_EXTENSIONS = (
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v',
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.opus', '.wma',
    '.ts', '.m3u8', '.mpd',
)

def normalize_url(url: str) -> str:
    """Extract the real URL from pasted text and strip problematic query params."""
    if not url:
        return ""

    cleaned = str(url).strip()
    if not cleaned:
        return ""

    match = re.search(r'https?://[^\s<>"\']+', cleaned, flags=re.IGNORECASE)
    if match:
        cleaned = match.group(0).rstrip('.,;)]}>')

    # Strip YouTube radio/playlist params that cause yt-dlp to hang
    try:
        parsed = urlparse(cleaned)
        if 'youtube.com' in (parsed.netloc or ''):
            params = parse_qs(parsed.query)
            for key in ['list', 'start_radio', 'index', 'pp']:
                params.pop(key, None)
            new_query = urlencode(params, doseq=True)
            cleaned = urlunparse(parsed._replace(query=new_query))
    except Exception:
        pass

    return cleaned


def is_direct_file_url(url: str) -> bool:
    """Check if a URL points directly to a downloadable media file."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in DIRECT_FILE_EXTENSIONS)
    except Exception:
        return False


def extract_filename_from_url(url: str) -> str:
    """Extract a clean filename from a direct file URL."""
    try:
        parsed = urlparse(url)
        filename = Path(parsed.path).name
        # Remove query params that might be attached
        filename = filename.split('?')[0]
        return sanitize_filename(filename) if filename else "download"
    except Exception:
        return "download"


def is_valid_url(url: str) -> bool:
    """Validate supported media URLs or direct file links."""
    cleaned = normalize_url(url)
    if not cleaned:
        return False

    try:
        result = urlparse(cleaned)
        if not all([result.scheme, result.netloc]):
            return False

        # Direct file URLs from any domain are accepted
        if is_direct_file_url(cleaned):
            return True

        # Otherwise check supported platforms
        valid_domains = [
            'youtube.com', 'youtu.be', 'vimeo.com',
            'soundcloud.com', 'twitter.com', 'x.com',
            'facebook.com', 'instagram.com', 'tiktok.com'
        ]
        return any(domain in result.netloc.lower() for domain in valid_domains)
    except ValueError:
        return False

def sanitize_filename(filename: str) -> str:
    """Sanitize string to be used as a safe filename."""
    if not filename:
        return "download"
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.strip()
    return clean if clean else "download"

def check_ffmpeg() -> bool:
    """Check if FFmpeg is available on the system."""
    return shutil.which('ffmpeg') is not None
