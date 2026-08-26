import os
import yt_dlp
import uuid
import threading
import time
from pathlib import Path
from config import DOWNLOAD_DIR, JOB_EXPIRATION, MAX_CONCURRENT_DOWNLOADS
from utils import logger, sanitize_filename

# ---------------------------------------------------------------------------
# In-memory job store — protected by jobs_lock
# ---------------------------------------------------------------------------
jobs: dict = {}
jobs_lock = threading.Lock()

# stop_events also protected by the same lock
_stop_events: dict = {}


class Downloader:
    """
    Manages background download jobs using yt-dlp.

    Each job is identified by a UUID (job_id).
    Jobs are stored in the module-level `jobs` dict and cleaned up after expiration.
    """

    # ------------------------------------------------------------------
    # Job lifecycle helpers
    # ------------------------------------------------------------------

    def clean_old_jobs(self) -> None:
        """
        Remove jobs that have been in a terminal state for longer than JOB_EXPIRATION.
        Also removes associated files from disk (outside the lock to avoid blocking).
        """
        now = time.time()
        files_to_delete: list[str] = []
        partial_job_ids: list[str] = []
        expired_keys: list[str] = []

        with jobs_lock:
            for job_id, job in jobs.items():
                if job['status'] in ('completed', 'cancelled', 'failed'):
                    if now - job.get('updated_at', now) > JOB_EXPIRATION:
                        expired_keys.append(job_id)
                        if job.get('filename'):
                            files_to_delete.append(job['filename'])
                        partial_job_ids.append(job_id)

            for key in expired_keys:
                del jobs[key]
                _stop_events.pop(key, None)

        # File I/O outside the lock — avoids blocking other threads
        download_dir = Path(DOWNLOAD_DIR)
        for fname in files_to_delete:
            fpath = download_dir / fname
            if fpath.is_file():
                try:
                    fpath.unlink()
                    logger.info(f"Deleted expired file: {fname}")
                except OSError as exc:
                    logger.warning(f"Could not delete {fname}: {exc}")

        # Remove any leftover .part / temp files for expired job IDs
        if partial_job_ids and download_dir.is_dir():
            for f in list(download_dir.iterdir()):
                for job_id in partial_job_ids:
                    if job_id in f.name:
                        try:
                            f.unlink()
                        except OSError:
                            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_video_info(self, url: str) -> dict:
        """
        Extract metadata from a URL using yt-dlp WITHOUT downloading the media.
        Returns a dict with 'success' True/False and either metadata or an error.
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Build format list from actual available formats
            seen_heights: set = set()
            format_options: list[dict] = []

            # Always include "Best Available"
            format_options.append({'id': 'best', 'label': 'Best Available (MP4)'})

            # Add specific quality options where they exist
            for f in info.get('formats', []):
                height = f.get('height')
                if height and f.get('vcodec', 'none') != 'none' and height not in seen_heights:
                    seen_heights.add(height)
                    format_options.append({
                        'id': f'height_{height}',
                        'label': f'{height}p',
                    })

            # Sort quality options descending (best first), after "Best Available"
            quality_entries = [x for x in format_options if x['id'] != 'best']
            quality_entries.sort(key=lambda x: int(x['id'].split('_')[1]), reverse=True)
            format_options = [{'id': 'best', 'label': 'Best Available (MP4)'}] + quality_entries

            # Audio-only always available
            format_options.append({'id': 'audio_only', 'label': 'Audio Only (MP3)'})

            return {
                'success': True,
                'title': info.get('title', 'Unknown Title'),
                'uploader': info.get('uploader') or info.get('channel', 'Unknown Channel'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': format_options,
            }

        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            logger.error(f"yt-dlp DownloadError fetching info for {url}: {msg}")
            if 'Private video' in msg or 'private' in msg.lower():
                user_msg = 'This video is private and cannot be accessed.'
            elif 'not available' in msg.lower() or 'unavailable' in msg.lower():
                user_msg = 'This video is not available.'
            else:
                user_msg = 'Unable to fetch video information. Ensure the video is public and the URL is correct.'
            return {'success': False, 'error': {'code': 'FETCH_ERROR', 'message': user_msg}}

        except Exception as exc:
            logger.error(f"Unexpected error fetching info for {url}: {exc}")
            return {'success': False, 'error': {'code': 'FETCH_ERROR', 'message': 'Unable to fetch video information.'}}

    def start_download(self, url: str, format_choice: str) -> str:
        """
        Create a new download job, start it in a background thread, and return the job_id.
        Raises an Exception if the concurrent download limit is reached.
        """
        self.clean_old_jobs()
        job_id = str(uuid.uuid4())

        with jobs_lock:
            active = sum(
                1 for j in jobs.values()
                if j['status'] in ('queued', 'downloading', 'processing')
            )
            if active >= MAX_CONCURRENT_DOWNLOADS:
                raise Exception('MAX_CONCURRENT_DOWNLOADS_REACHED')

            jobs[job_id] = {
                'job_id': job_id,
                'status': 'queued',
                'progress': 0,
                'speed': '',
                'eta': '',
                'filename': '',
                'error': '',
                'updated_at': time.time(),
            }
            stop_event = threading.Event()
            _stop_events[job_id] = stop_event

        thread = threading.Thread(
            target=self._download_worker,
            args=(job_id, url, format_choice, stop_event),
            daemon=True,
        )
        thread.start()
        return job_id

    def get_job_status(self, job_id: str) -> dict | None:
        """Return the job dict for job_id, or None if not found."""
        with jobs_lock:
            job = jobs.get(job_id)
            # Return a shallow copy so the caller cannot mutate shared state
            return dict(job) if job else None

    def cancel_job(self, job_id: str) -> bool:
        """
        Signal the download thread to stop.
        Returns True if the job existed and was signalled, False otherwise.
        """
        with jobs_lock:
            if job_id not in _stop_events:
                return False
            _stop_events[job_id].set()
            if job_id in jobs:
                jobs[job_id]['status'] = 'cancelled'
                jobs[job_id]['updated_at'] = time.time()
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _progress_hook(self, d: dict, job_id: str, stop_event: threading.Event) -> None:
        """
        Called by yt-dlp during download to report progress.
        Raises an exception to stop yt-dlp if cancellation has been requested.
        """
        if stop_event.is_set():
            raise Exception('DOWNLOAD_CANCELLED')

        with jobs_lock:
            if job_id not in jobs:
                return

            jobs[job_id]['updated_at'] = time.time()

            if d['status'] == 'downloading':
                jobs[job_id]['status'] = 'downloading'

                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total and total > 0:
                    jobs[job_id]['progress'] = round(downloaded / total * 100, 1)

                speed = d.get('speed')
                if speed:
                    jobs[job_id]['speed'] = f"{speed / 1_048_576:.1f} MB/s"

                eta = d.get('eta')
                if eta is not None and isinstance(eta, (int, float)):
                    m, s = divmod(int(eta), 60)
                    h, m = divmod(m, 60)
                    if h:
                        jobs[job_id]['eta'] = f"{h:02d}:{m:02d}:{s:02d}"
                    else:
                        jobs[job_id]['eta'] = f"{m:02d}:{s:02d}"

            elif d['status'] == 'finished':
                jobs[job_id]['status'] = 'processing'
                jobs[job_id]['progress'] = 100

    def _build_format_string(self, format_choice: str) -> str:
        """
        Convert the user-facing format choice into a yt-dlp format string.
        Falls back gracefully if the requested height is not available.
        """
        if format_choice == 'audio_only':
            return 'bestaudio/best'

        if format_choice.startswith('height_'):
            try:
                height = int(format_choice.split('_')[1])
                # Try exact height, then fall back to best available
                return (
                    f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]'
                    f'/bestvideo[height<={height}]+bestaudio'
                    f'/best[height<={height}]'
                    f'/bestvideo[ext=mp4]+bestaudio[ext=m4a]'
                    f'/best'
                )
            except (ValueError, IndexError):
                pass

        # Default: best quality MP4
        return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    def _download_worker(
        self,
        job_id: str,
        url: str,
        format_choice: str,
        stop_event: threading.Event,
    ) -> None:
        """
        Background thread: performs the actual download using yt-dlp.
        Updates the job dict on completion or failure.
        """
        logger.info(f"Job {job_id} starting — format={format_choice} url={url}")

        # Output template: title + job_id to guarantee uniqueness
        output_tmpl = str(Path(DOWNLOAD_DIR) / f'%(title)s_{job_id}.%(ext)s')

        ydl_opts: dict = {
            'outtmpl': output_tmpl,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [lambda d: self._progress_hook(d, job_id, stop_event)],
            'restrictfilenames': True,
            # Subtitle options
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'en-US', 'en-GB'],
            'embedsubtitles': True,
        }

        fmt_str = self._build_format_string(format_choice)

        if format_choice == 'audio_only':
            ydl_opts.update({
                'format': fmt_str,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': fmt_str,
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }, {
                    'key': 'FFmpegEmbedSubtitle',
                }],
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if stop_event.is_set():
                # Cancellation happened right at completion — treat as cancelled
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]['status'] = 'cancelled'
                        jobs[job_id]['updated_at'] = time.time()
                return

            # Determine the final filename on disk
            with yt_dlp.YoutubeDL({'outtmpl': output_tmpl, 'quiet': True}) as ydl2:
                prepared = ydl2.prepare_filename(info)

            final_path = Path(prepared)
            if format_choice == 'audio_only':
                final_path = final_path.with_suffix('.mp3')
            else:
                final_path = final_path.with_suffix('.mp4')

            basename = final_path.name

            # Sanity-check: file must actually exist in DOWNLOAD_DIR
            expected = Path(DOWNLOAD_DIR) / basename
            if not expected.is_file():
                # yt-dlp may have sanitized the title differently — search by job_id in name
                matches = list(Path(DOWNLOAD_DIR).glob(f'*{job_id}*'))
                if matches:
                    basename = matches[0].name
                else:
                    raise FileNotFoundError(f"Output file not found for job {job_id}")

            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['filename'] = basename
                    jobs[job_id]['progress'] = 100
                    jobs[job_id]['updated_at'] = time.time()

            logger.info(f"Job {job_id} completed — file: {basename}")

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Job {job_id} failed: {err_msg}")

            with jobs_lock:
                if job_id in jobs:
                    if 'DOWNLOAD_CANCELLED' in err_msg:
                        jobs[job_id]['status'] = 'cancelled'
                        jobs[job_id]['error'] = ''
                    elif 'ffmpeg' in err_msg.lower() or 'FFmpeg' in err_msg:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = (
                            'FFmpeg is required for this format but was not found. '
                            'Please install FFmpeg and try again.'
                        )
                    elif 'Private video' in err_msg or 'private' in err_msg.lower():
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = 'This video is private and cannot be downloaded.'
                    elif 'not available' in err_msg.lower():
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = 'This video is not available in your region or has been removed.'
                    else:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = 'Download failed. The video may be unavailable or require FFmpeg.'
                    jobs[job_id]['updated_at'] = time.time()

            # Clean up any partial files left by yt-dlp
            try:
                for f in Path(DOWNLOAD_DIR).glob(f'*{job_id}*'):
                    f.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Singleton instance used by app.py
# ---------------------------------------------------------------------------
downloader = Downloader()
