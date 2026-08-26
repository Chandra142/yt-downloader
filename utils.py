import re
from urllib.parse import urlparse
import shutil
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ytdownloader')

def normalize_url(url: str) -> str:
    """Extract the real URL from pasted text like '1 = https://...'"""
    if not url:
        return ""

    cleaned = str(url).strip()
    if not cleaned:
        return ""

    match = re.search(r'https?://[^\s<>"\']+', cleaned, flags=re.IGNORECASE)
    if match:
        cleaned = match.group(0).rstrip('.,;)]}>')

    return cleaned


def is_valid_url(url: str) -> bool:
    """Validate supported media URLs, allowing pasted labels like '1 = https://...'"""
    cleaned = normalize_url(url)
    if not cleaned:
        return False

    try:
        result = urlparse(cleaned)
        if not all([result.scheme, result.netloc]):
            return False

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
