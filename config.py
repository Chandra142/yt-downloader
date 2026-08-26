import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / os.getenv('DOWNLOAD_DIR', 'downloads')
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '5'))
JOB_EXPIRATION = int(os.getenv('JOB_EXPIRATION', '3600')) # seconds
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('FLASK_ENV', 'development') == 'development'
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:5000').rstrip('/')

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
