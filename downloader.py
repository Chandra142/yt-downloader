import os
import yt_dlp
import uuid
import threading
import time
import requests
from pathlib import Path
from config import DOWNLOAD_DIR, JOB_EXPIRATION, MAX_CONCURRENT_DOWNLOADS
from utils import logger, sanitize_filename, is_direct_file_url, extract_filename_from_url

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
        # Handle direct file URLs
        if is_direct_file_url(url):
            return self._get_direct_file_info(url)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
            'extract_retries': 2,
            'retries': 2,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
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

    def _get_direct_file_info(self, url: str) -> dict:
        """Get metadata for a direct file URL by checking headers."""
        try:
            resp = requests.head(
                url,
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            )
            resp.raise_for_status()

            content_length = int(resp.headers.get('Content-Length', 0))
            content_type = resp.headers.get('Content-Type', '')
            filename = extract_filename_from_url(url)

            # Format file size
            filesize = self._format_bytes(content_length) if content_length else 'Unknown'

            return {
                'success': True,
                'title': filename,
                'uploader': 'Direct Link',
                'duration': 0,
                'thumbnail': '',
                'formats': [
                    {'id': 'direct', 'label': f'Download ({filesize})'},
                ],
            }

        except requests.RequestException as exc:
            logger.error(f"Failed to fetch direct file info for {url}: {exc}")
            return {'success': False, 'error': {'code': 'FETCH_ERROR', 'message': 'Could not access the file. The link may be expired or invalid.'}}

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
                'url': url,
                'updated_at': time.time(),
                'started_at': time.time(),
                'downloaded_bytes': 0,
                'total_bytes': 0,
                'elapsed': '',
                'filesize': '',
                'fragment': '',
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

    def resume_download(self, job_id: str) -> bool:
        """
        Resume a failed/cancelled direct file download from where it left off.
        Returns True if resumed, False if job not found or not resumable.
        """
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                return False

            # Only resumable if it was a direct download that failed/cancelled
            url = job.get('url', '')
            if not url or not is_direct_file_url(url):
                return False
            if job['status'] not in ('failed', 'cancelled'):
                return False

            downloaded = job.get('downloaded_bytes', 0)
            if downloaded <= 0:
                return False

            # Reset job state for resume
            job['status'] = 'queued'
            job['error'] = ''
            job['updated_at'] = time.time()
            job['started_at'] = time.time()

            stop_event = threading.Event()
            _stop_events[job_id] = stop_event

        thread = threading.Thread(
            target=self._download_direct_resume,
            args=(job_id, url, stop_event),
            daemon=True,
        )
        thread.start()
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

            job = jobs[job_id]
            job['updated_at'] = time.time()

            if d['status'] == 'downloading':
                job['status'] = 'downloading'

                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)

                job['downloaded_bytes'] = downloaded
                job['total_bytes'] = total

                if total and total > 0:
                    job['progress'] = round(downloaded / total * 100, 1)
                    job['filesize'] = self._format_bytes(total)
                elif downloaded > 0:
                    job['filesize'] = f"~{self._format_bytes(downloaded)}"

                if downloaded > 0:
                    job['fragment'] = self._format_bytes(downloaded)

                speed = d.get('speed')
                if speed:
                    job['speed'] = f"{speed / 1_048_576:.1f} MB/s"

                eta = d.get('eta')
                if eta is not None and isinstance(eta, (int, float)):
                    m, s = divmod(int(eta), 60)
                    h, m = divmod(m, 60)
                    if h:
                        job['eta'] = f"{h:02d}:{m:02d}:{s:02d}"
                    else:
                        job['eta'] = f"{m:02d}:{s:02d}"

                # Elapsed time since download started
                elapsed_secs = time.time() - job.get('started_at', job['updated_at'])
                em, es = divmod(int(elapsed_secs), 60)
                eh, em = divmod(em, 60)
                if eh:
                    job['elapsed'] = f"{eh:02d}:{em:02d}:{es:02d}"
                else:
                    job['elapsed'] = f"{em:02d}:{es:02d}"

            elif d['status'] == 'finished':
                job['status'] = 'processing'
                job['progress'] = 100

    @staticmethod
    def _format_bytes(n: int) -> str:
        """Format bytes into human-readable string."""
        if n <= 0:
            return "0 B"
        for unit in ('B', 'KB', 'MB', 'GB'):
            if abs(n) < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

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
        Background thread: performs the actual download using yt-dlp or direct HTTP.
        Updates the job dict on completion or failure.
        """
        logger.info(f"Job {job_id} starting — format={format_choice} url={url}")

        # Direct file download
        if is_direct_file_url(url):
            self._download_direct(job_id, url, stop_event)
            return

        # yt-dlp download
        self._download_ytdlp(job_id, url, format_choice, stop_event)

    def _download_direct(
        self,
        job_id: str,
        url: str,
        stop_event: threading.Event,
    ) -> None:
        """Download a direct file URL using requests with streaming."""
        filename = extract_filename_from_url(url)
        # Append job_id to avoid collisions
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2:
            safe_name = f"{name_parts[0]}_{job_id}.{name_parts[1]}"
        else:
            safe_name = f"{filename}_{job_id}"

        filepath = Path(DOWNLOAD_DIR) / safe_name

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)
            resp.raise_for_status()

            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192
            start_time = time.time()

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if stop_event.is_set():
                        with jobs_lock:
                            if job_id in jobs:
                                jobs[job_id]['status'] = 'cancelled'
                                jobs[job_id]['updated_at'] = time.time()
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress
                        with jobs_lock:
                            if job_id not in jobs:
                                return
                            job = jobs[job_id]
                            job['updated_at'] = time.time()
                            job['status'] = 'downloading'
                            job['downloaded_bytes'] = downloaded
                            job['total_bytes'] = total
                            job['fragment'] = self._format_bytes(downloaded)

                            if total > 0:
                                job['progress'] = round(downloaded / total * 100, 1)
                                job['filesize'] = self._format_bytes(total)
                            else:
                                job['filesize'] = f"~{self._format_bytes(downloaded)}"

                            elapsed_secs = time.time() - job.get('started_at', job['updated_at'])
                            em, es = divmod(int(elapsed_secs), 60)
                            eh, em = divmod(em, 60)
                            job['elapsed'] = f"{eh:02d}:{em:02d}:{es:02d}" if eh else f"{em:02d}:{es:02d}"

                            if downloaded > 0 and elapsed_secs > 2:
                                speed = downloaded / elapsed_secs
                                job['speed'] = f"{speed / 1_048_576:.1f} MB/s"
                                if total > 0 and speed > 0:
                                    remaining = (total - downloaded) / speed
                                    rm, rs = divmod(int(remaining), 60)
                                    rh, rm = divmod(rm, 60)
                                    job['eta'] = f"{rh:02d}:{rm:02d}:{rs:02d}" if rh else f"{rm:02d}:{rs:02d}"

            if stop_event.is_set():
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]['status'] = 'cancelled'
                        jobs[job_id]['updated_at'] = time.time()
                return

            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['filename'] = safe_name
                    jobs[job_id]['progress'] = 100
                    jobs[job_id]['updated_at'] = time.time()

            logger.info(f"Job {job_id} completed (direct) — file: {safe_name}")

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Job {job_id} failed (direct): {err_msg}")

            with jobs_lock:
                if job_id in jobs:
                    if 'DOWNLOAD_CANCELLED' in err_msg:
                        jobs[job_id]['status'] = 'cancelled'
                    else:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = f'Download failed: {err_msg[:100]}'
                    jobs[job_id]['updated_at'] = time.time()

            # Clean up partial file
            try:
                if filepath.is_file():
                    filepath.unlink(missing_ok=True)
            except OSError:
                pass

    def _download_direct_resume(
        self,
        job_id: str,
        url: str,
        stop_event: threading.Event,
    ) -> None:
        """Resume a direct file download from a previous byte offset."""
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                return
            existing_bytes = job.get('downloaded_bytes', 0)
            safe_name = job.get('filename', '')

        if not safe_name:
            # Rebuild filename
            filename = extract_filename_from_url(url)
            name_parts = filename.rsplit('.', 1)
            if len(name_parts) == 2:
                safe_name = f"{name_parts[0]}_{job_id}.{name_parts[1]}"
            else:
                safe_name = f"{filename}_{job_id}"

        filepath = Path(DOWNLOAD_DIR) / safe_name

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Range': f'bytes={existing_bytes}-',
            }
            resp = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)
            resp.raise_for_status()

            total = int(resp.headers.get('Content-Length', 0)) + existing_bytes
            downloaded = existing_bytes
            chunk_size = 8192

            with open(filepath, 'ab') as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if stop_event.is_set():
                        with jobs_lock:
                            if job_id in jobs:
                                jobs[job_id]['status'] = 'cancelled'
                                jobs[job_id]['downloaded_bytes'] = downloaded
                                jobs[job_id]['updated_at'] = time.time()
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        with jobs_lock:
                            if job_id not in jobs:
                                return
                            job = jobs[job_id]
                            job['updated_at'] = time.time()
                            job['status'] = 'downloading'
                            job['downloaded_bytes'] = downloaded
                            job['total_bytes'] = total
                            job['filename'] = safe_name
                            job['fragment'] = self._format_bytes(downloaded)

                            if total > 0:
                                job['progress'] = round(downloaded / total * 100, 1)
                                job['filesize'] = self._format_bytes(total)
                            else:
                                job['filesize'] = f"~{self._format_bytes(downloaded)}"

                            elapsed_secs = time.time() - job.get('started_at', job['updated_at'])
                            em, es = divmod(int(elapsed_secs), 60)
                            eh, em = divmod(em, 60)
                            job['elapsed'] = f"{eh:02d}:{em:02d}:{es:02d}" if eh else f"{em:02d}:{es:02d}"

                            # Speed based on new bytes only (excluding existing)
                            new_bytes = downloaded - existing_bytes
                            if new_bytes > 0 and elapsed_secs > 2:
                                speed = new_bytes / elapsed_secs
                                job['speed'] = f"{speed / 1_048_576:.1f} MB/s"
                                if total > 0 and speed > 0:
                                    remaining = (total - downloaded) / speed
                                    rm, rs = divmod(int(remaining), 60)
                                    rh, rm = divmod(rm, 60)
                                    job['eta'] = f"{rh:02d}:{rm:02d}:{rs:02d}" if rh else f"{rm:02d}:{rs:02d}"

            if stop_event.is_set():
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]['status'] = 'cancelled'
                        jobs[job_id]['updated_at'] = time.time()
                return

            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['filename'] = safe_name
                    jobs[job_id]['progress'] = 100
                    jobs[job_id]['updated_at'] = time.time()

            logger.info(f"Job {job_id} completed (resumed) — file: {safe_name}")

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Job {job_id} failed (resume): {err_msg}")

            with jobs_lock:
                if job_id in jobs:
                    if 'DOWNLOAD_CANCELLED' in err_msg:
                        jobs[job_id]['status'] = 'cancelled'
                    else:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['error'] = f'Download failed: {err_msg[:100]}'
                    jobs[job_id]['downloaded_bytes'] = downloaded
                    jobs[job_id]['updated_at'] = time.time()

    def _download_ytdlp(
        self,
        job_id: str,
        url: str,
        format_choice: str,
        stop_event: threading.Event,
    ) -> None:
        """Download using yt-dlp for platform URLs."""
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
