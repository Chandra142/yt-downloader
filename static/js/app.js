/**
 * app.js — YT Downloader Frontend
 *
 * Flow:
 *   1. User enters URL → clicks "Get Video"
 *   2. POST /api/info → display metadata
 *   3. User clicks "Download" → POST /api/download → receive job_id
 *   4. Poll GET /api/progress/<job_id> every second
 *   5. On complete → show "Save File" link to GET /download/<job_id>
 */

document.addEventListener('DOMContentLoaded', () => {

    // ----------------------------------------------------------------
    // Theme persistence
    // ----------------------------------------------------------------
    const themeCheckbox = document.getElementById('theme-checkbox');
    const savedTheme = localStorage.getItem('yt-theme') || 'light-mode';
    document.body.className = savedTheme;
    themeCheckbox.checked = (savedTheme === 'dark-mode');

    themeCheckbox.addEventListener('change', () => {
        const theme = themeCheckbox.checked ? 'dark-mode' : 'light-mode';
        document.body.className = theme;
        localStorage.setItem('yt-theme', theme);
    });

    // ----------------------------------------------------------------
    // Element refs
    // ----------------------------------------------------------------
    const urlInput          = document.getElementById('url-input');
    const fetchBtn          = document.getElementById('fetch-btn');
    const pasteBtn          = document.getElementById('paste-btn');
    const urlError          = document.getElementById('url-error');

    const metadataSection   = document.getElementById('metadata-section');
    const videoThumbnail    = document.getElementById('video-thumbnail');
    const videoTitle        = document.getElementById('video-title');
    const videoChannel      = document.getElementById('video-channel');
    const videoDuration     = document.getElementById('video-duration');
    const formatSelect      = document.getElementById('format-select');
    const downloadBtn       = document.getElementById('download-btn');

    const progressSection   = document.getElementById('progress-section');
    const progressStatus    = document.getElementById('progress-status');
    const progressBar       = document.getElementById('progress-bar');
    const progressAria      = document.getElementById('progress-aria');
    const progressPercent   = document.getElementById('progress-percent');
    const progressSpeed     = document.getElementById('progress-speed');
    const progressEta       = document.getElementById('progress-eta');
    const progressFragment  = document.getElementById('progress-fragment');
    const progressFilesize  = document.getElementById('progress-filesize');
    const progressElapsed   = document.getElementById('progress-elapsed');
    const progressRemaining = document.getElementById('progress-remaining');
    const cancelBtn         = document.getElementById('cancel-btn');
    const resumeBtn         = document.getElementById('resume-btn');
    const saveFileBtn       = document.getElementById('save-file-btn');
    const copyLinkBtn       = document.getElementById('copy-link-btn');
    const completedActions  = document.getElementById('completed-actions');
    const newDownloadBtn    = document.getElementById('new-download-btn');

    const inputGroup        = document.querySelector('.input-group');
    const toastContainer    = document.getElementById('toast-container');

    // ----------------------------------------------------------------
    // State
    // ----------------------------------------------------------------
    let currentJobId    = null;
    let pollIntervalId  = null;
    let currentUrl      = '';

    // ----------------------------------------------------------------
    // Toast notifications
    // ----------------------------------------------------------------
    function showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // ----------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------

    function showUrlError(msg) {
        urlError.textContent = msg;
        urlError.classList.remove('hidden');
    }

    function clearUrlError() {
        urlError.textContent = '';
        urlError.classList.add('hidden');
    }

    function setFetchingState(fetching) {
        fetchBtn.disabled = fetching;
        if (fetching) {
            fetchBtn.innerHTML = '<span class="spinner"></span> Fetching…';
        } else {
            fetchBtn.textContent = 'Get Video';
        }
    }

    function setDownloadingState(active) {
        downloadBtn.disabled = active;
        if (active) {
            downloadBtn.innerHTML = '<span class="spinner"></span> Downloading…';
        } else {
            downloadBtn.textContent = '⬇ Download';
        }
        cancelBtn.classList.toggle('hidden', !active);
    }

    function formatDuration(seconds) {
        if (!seconds || isNaN(seconds)) return '00:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function setProgress(pct) {
        const val = Math.min(100, Math.max(0, pct));
        progressBar.style.width = `${val}%`;
        progressAria.setAttribute('aria-valuenow', val);
        progressPercent.textContent = `${val}%`;
    }

    function stopPolling() {
        if (pollIntervalId) {
            clearInterval(pollIntervalId);
            pollIntervalId = null;
        }
    }

    function resetToIdle() {
        clearUrlError();
        metadataSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        setProgress(0);
        progressStatus.textContent = 'Preparing…';
        progressSpeed.textContent = '';
        progressEta.textContent = 'ETA: --:--';
        progressFragment.textContent = '0 B';
        progressFilesize.textContent = '—';
        progressElapsed.textContent = '00:00';
        progressRemaining.textContent = '—';
        completedActions.classList.add('hidden');
        resumeBtn.classList.add('hidden');
        saveFileBtn.classList.add('hidden');
        saveFileBtn.href = '#';
        copyLinkBtn.classList.add('hidden');
        newDownloadBtn.classList.add('hidden');
        cancelBtn.classList.remove('hidden');
        cancelBtn.disabled = false;
        resumeBtn.disabled = false;
        resumeBtn.innerHTML = '▶ Resume';
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = '⬇ Download';
        currentJobId = null;
        stopPolling();
    }

    // ----------------------------------------------------------------
    // Clipboard paste
    // ----------------------------------------------------------------
    pasteBtn.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                urlInput.value = text.trim();
                urlInput.focus();
                showToast('URL pasted from clipboard', 'success', 1500);
            }
        } catch (err) {
            showToast('Could not access clipboard. Use Ctrl+V instead.', 'error');
        }
    });

    // Ctrl+V paste handler for the whole page
    document.addEventListener('paste', (e) => {
        if (document.activeElement === urlInput) return;
        const text = (e.clipboardData || window.clipboardData).getData('text');
        if (text) {
            urlInput.value = text.trim();
            urlInput.focus();
            showToast('URL pasted from clipboard', 'success', 1500);
        }
    });

    // ----------------------------------------------------------------
    // Drag and drop URL
    // ----------------------------------------------------------------
    inputGroup.addEventListener('dragover', (e) => {
        e.preventDefault();
        inputGroup.classList.add('drag-over');
    });

    inputGroup.addEventListener('dragleave', () => {
        inputGroup.classList.remove('drag-over');
    });

    inputGroup.addEventListener('drop', (e) => {
        e.preventDefault();
        inputGroup.classList.remove('drag-over');
        const text = e.dataTransfer.getData('text/plain');
        if (text) {
            urlInput.value = text.trim();
            showToast('URL dropped', 'success', 1500);
        }
    });

    // ----------------------------------------------------------------
    // Keyboard shortcuts
    // ----------------------------------------------------------------
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (!progressSection.classList.contains('hidden') && !cancelBtn.classList.contains('hidden') && currentJobId) {
                cancelBtn.click();
            }
        }
    });

    // ----------------------------------------------------------------
    // Fetch video info
    // ----------------------------------------------------------------
    fetchBtn.addEventListener('click', fetchInfo);
    urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchInfo(); });

    async function fetchInfo() {
        const url = urlInput.value.trim();
        if (!url) {
            showUrlError('Please enter a URL.');
            urlInput.focus();
            return;
        }

        clearUrlError();
        setFetchingState(true);
        metadataSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        stopPolling();
        currentUrl = url;

        try {
            const res = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            const data = await res.json();

            if (!data.success) {
                showUrlError(data.error?.message || 'Failed to fetch video information.');
                return;
            }

            renderMetadata(data);
            showToast('Video found!', 'success', 2000);

        } catch (err) {
            showUrlError('Network error. Please check your connection and try again.');
        } finally {
            setFetchingState(false);
        }
    }

    function renderMetadata(data) {
        // Thumbnail
        if (data.thumbnail) {
            videoThumbnail.src = data.thumbnail;
            videoThumbnail.style.display = '';
        } else {
            videoThumbnail.style.display = 'none';
        }

        videoTitle.textContent   = data.title || 'Unknown Title';
        videoChannel.textContent = data.uploader || 'Unknown Channel';
        videoDuration.textContent = formatDuration(data.duration);

        // Populate format selector from server response
        formatSelect.innerHTML = '';
        (data.formats || []).forEach(f => {
            const opt = document.createElement('option');
            opt.value       = f.id || f.format_id || 'best';
            opt.textContent = f.label || `${f.resolution || ''} (${f.ext || ''}) ${f.note || ''}`.trim();
            formatSelect.appendChild(opt);
        });

        metadataSection.classList.remove('hidden');
    }

    // ----------------------------------------------------------------
    // Start download
    // ----------------------------------------------------------------
    downloadBtn.addEventListener('click', startDownload);

    async function startDownload() {
        if (!currentUrl) {
            showUrlError('Please fetch a video first.');
            return;
        }

        const format = formatSelect.value;

        // Transition to progress view
        metadataSection.classList.add('hidden');
        progressSection.classList.remove('hidden');
        completedActions.classList.add('hidden');
        setProgress(0);
        progressStatus.textContent = 'Starting…';
        progressSpeed.textContent  = '';
        progressEta.textContent    = 'ETA: --:--';
        newDownloadBtn.classList.add('hidden');
        cancelBtn.classList.remove('hidden');
        setDownloadingState(true);
        currentJobId = null;

        try {
            const res = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: currentUrl, format }),
            });
            const data = await res.json();

            if (!data.success) {
                progressStatus.textContent = `Error: ${data.error?.message || 'Failed to start download.'}`;
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                completedActions.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                showToast('Failed to start download', 'error');
                return;
            }

            currentJobId = data.job_id;
            startPolling();

        } catch (err) {
            progressStatus.textContent = 'Network error while starting download.';
            setDownloadingState(false);
            cancelBtn.classList.add('hidden');
            completedActions.classList.remove('hidden');
            newDownloadBtn.classList.remove('hidden');
            showToast('Network error', 'error');
        }
    }

    // ----------------------------------------------------------------
    // Progress polling
    // ----------------------------------------------------------------
    function startPolling() {
        stopPolling(); // ensure no duplicate intervals
        pollIntervalId = setInterval(pollProgress, 1000);
    }

    async function pollProgress() {
        if (!currentJobId) {
            stopPolling();
            return;
        }

        try {
            const res = await fetch(`/api/progress/${currentJobId}`);
            const data = await res.json();

            if (!data.success) {
                // Job expired or not found
                stopPolling();
                progressStatus.textContent = 'Job expired or not found.';
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                completedActions.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                return;
            }

            handleProgressUpdate(data);

        } catch (err) {
            // Network hiccup — keep polling, don't abort
            console.warn('Progress poll failed (will retry):', err.message);
        }
    }

    function handleProgressUpdate(data) {
        const { status, progress, speed, eta, error, filesize, elapsed, fragment } = data;

        switch (status) {
            case 'queued':
                progressStatus.textContent = 'Queued…';
                break;

            case 'downloading':
                progressStatus.textContent = 'Downloading…';
                setProgress(progress || 0);
                progressSpeed.textContent  = speed || '';
                progressEta.textContent    = eta ? `ETA: ${eta}` : 'ETA: --:--';
                progressFragment.textContent = fragment || '0 B';
                progressFilesize.textContent = filesize || '—';
                progressElapsed.textContent  = elapsed || '00:00';
                progressRemaining.textContent = eta || '—';
                break;

            case 'processing':
                progressStatus.textContent = 'Processing… (merging video & audio)';
                setProgress(100);
                progressSpeed.textContent  = '';
                progressEta.textContent    = '';
                progressRemaining.textContent = '—';
                break;

            case 'completed':
                stopPolling();
                setProgress(100);
                progressStatus.textContent = '✓ Download Ready!';
                progressSpeed.textContent  = '';
                progressEta.textContent    = '';
                progressRemaining.textContent = '—';
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                resumeBtn.classList.add('hidden');
                saveFileBtn.href = `/download/${currentJobId}`;
                saveFileBtn.classList.remove('hidden');
                copyLinkBtn.classList.remove('hidden');
                completedActions.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                showToast('Download complete!', 'success');
                break;

            case 'cancelled':
                stopPolling();
                progressStatus.textContent = 'Download cancelled.';
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                completedActions.classList.remove('hidden');
                resumeBtn.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                break;

            case 'failed':
                stopPolling();
                progressStatus.textContent = `Failed: ${error || 'An unknown error occurred.'}`;
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                completedActions.classList.remove('hidden');
                resumeBtn.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                showToast('Download failed', 'error');
                break;

            default:
                break;
        }
    }

    // ----------------------------------------------------------------
    // Cancel
    // ----------------------------------------------------------------
    cancelBtn.addEventListener('click', async () => {
        if (!currentJobId) return;

        cancelBtn.disabled = true;

        try {
            const res = await fetch(`/api/cancel/${currentJobId}`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                stopPolling();
                progressStatus.textContent = 'Download cancelled.';
                setDownloadingState(false);
                cancelBtn.classList.add('hidden');
                completedActions.classList.remove('hidden');
                resumeBtn.classList.remove('hidden');
                newDownloadBtn.classList.remove('hidden');
                showToast('Download cancelled', 'info');
            } else {
                cancelBtn.disabled = false;
            }
        } catch (err) {
            cancelBtn.disabled = false;
            console.error('Cancel request failed:', err.message);
        }
    });

    // ----------------------------------------------------------------
    // Resume download
    // ----------------------------------------------------------------
    resumeBtn.addEventListener('click', async () => {
        if (!currentJobId) return;

        resumeBtn.disabled = true;
        resumeBtn.innerHTML = '<span class="spinner"></span> Resuming…';

        try {
            const res = await fetch(`/api/resume/${currentJobId}`, { method: 'POST' });
            const data = await res.json();

            if (data.success) {
                resumeBtn.classList.add('hidden');
                saveFileBtn.classList.add('hidden');
                copyLinkBtn.classList.add('hidden');
                cancelBtn.classList.remove('hidden');
                cancelBtn.disabled = false;
                setProgress(0);
                progressStatus.textContent = 'Resuming…';
                progressSpeed.textContent = '';
                progressEta.textContent = 'ETA: --:--';
                startPolling();
                showToast('Download resuming…', 'info');
            } else {
                resumeBtn.disabled = false;
                resumeBtn.innerHTML = '▶ Resume';
                showToast(data.error?.message || 'Cannot resume this download.', 'error');
            }
        } catch (err) {
            resumeBtn.disabled = false;
            resumeBtn.innerHTML = '▶ Resume';
            console.error('Resume request failed:', err.message);
        }
    });

    // ----------------------------------------------------------------
    // Copy download link
    // ----------------------------------------------------------------
    copyLinkBtn.addEventListener('click', async () => {
        if (!currentJobId) return;
        const link = `${window.location.origin}/download/${currentJobId}`;
        try {
            await navigator.clipboard.writeText(link);
            showToast('Download link copied!', 'success', 2000);
        } catch (err) {
            showToast('Could not copy link', 'error');
        }
    });

    // ----------------------------------------------------------------
    // New download — reset UI
    // ----------------------------------------------------------------
    newDownloadBtn.addEventListener('click', () => {
        resetToIdle();
        urlInput.value = '';
        urlInput.focus();
    });

});