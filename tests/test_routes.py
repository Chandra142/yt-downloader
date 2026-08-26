"""
test_routes.py — Flask route tests using the test client.

yt-dlp is NOT called in these tests — only routing and validation logic is exercised.
No real YouTube downloads are performed.
"""
import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ----------------------------------------------------------------
# Homepage
# ----------------------------------------------------------------

class TestHomePage:
    def test_homepage_status_200(self, client):
        rv = client.get('/')
        assert rv.status_code == 200

    def test_homepage_contains_title(self, client):
        rv = client.get('/')
        assert b'YT Downloader' in rv.data

    def test_homepage_has_security_headers(self, client):
        rv = client.get('/')
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'
        assert 'Referrer-Policy' in rv.headers
        assert 'X-Frame-Options' in rv.headers


# ----------------------------------------------------------------
# /api/info
# ----------------------------------------------------------------

class TestApiInfo:
    def test_rejects_non_json(self, client):
        rv = client.post('/api/info', data='not json', content_type='text/plain')
        assert rv.status_code == 400

    def test_rejects_empty_url(self, client):
        rv = client.post('/api/info', json={'url': ''})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'INVALID_URL'

    def test_rejects_invalid_url(self, client):
        rv = client.post('/api/info', json={'url': 'invalid_url'})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'INVALID_URL'

    def test_rejects_unsupported_domain(self, client):
        rv = client.post('/api/info', json={'url': 'https://example.com/video'})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'INVALID_URL'

    def test_rejects_very_long_url(self, client):
        rv = client.post('/api/info', json={'url': 'https://youtube.com/' + 'a' * 3000})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False

    def test_missing_url_key(self, client):
        rv = client.post('/api/info', json={})
        assert rv.status_code == 400


# ----------------------------------------------------------------
# /api/download
# ----------------------------------------------------------------

class TestApiDownload:
    def test_passes_selected_height_to_downloader(self, client, monkeypatch):
        captured = {}

        def start_download(url, format_choice):
            captured['url'] = url
            captured['format_choice'] = format_choice
            return 'test-job-id'

        monkeypatch.setattr('app.downloader.start_download', start_download)

        rv = client.post('/api/download', json={
            'url': 'https://youtube.com/watch?v=abc123',
            'format': 'height_720',
        })

        assert rv.status_code == 200
        assert captured['format_choice'] == 'height_720'

    def test_rejects_invalid_url(self, client):
        rv = client.post('/api/download', json={'url': 'bad_url', 'format': 'best'})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'INVALID_URL'

    def test_rejects_empty_url(self, client):
        rv = client.post('/api/download', json={'url': '', 'format': 'best'})
        assert rv.status_code == 400

    def test_rejects_non_json(self, client):
        rv = client.post('/api/download', data='not json', content_type='text/plain')
        assert rv.status_code == 400

    def test_rejects_very_long_url(self, client):
        rv = client.post('/api/download', json={'url': 'https://youtube.com/' + 'a' * 3000})
        assert rv.status_code == 400


# ----------------------------------------------------------------
# /api/cancel
# ----------------------------------------------------------------

class TestApiCancel:
    def test_cancel_nonexistent_job(self, client):
        rv = client.post('/api/cancel/non-existent-job-12345')
        assert rv.status_code == 404
        data = rv.get_json()
        assert data['success'] is False
        assert data['error'] == 'Job not found.'

    def test_cancel_with_very_long_id(self, client):
        rv = client.post('/api/cancel/' + 'x' * 200)
        assert rv.status_code == 400


# ----------------------------------------------------------------
# /api/progress
# ----------------------------------------------------------------

class TestApiProgress:
    def test_progress_nonexistent_job(self, client):
        rv = client.get('/api/progress/non-existent-job-00000')
        assert rv.status_code == 404
        data = rv.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'NOT_FOUND'

    def test_progress_very_long_id(self, client):
        rv = client.get('/api/progress/' + 'x' * 200)
        assert rv.status_code == 400


# ----------------------------------------------------------------
# /download/<job_id> — file serving security
# ----------------------------------------------------------------

class TestServeDownload:
    def test_nonexistent_job_returns_404(self, client):
        rv = client.get('/download/fake-job-id-99999')
        assert rv.status_code == 404

    def test_very_long_job_id_returns_400(self, client):
        rv = client.get('/download/' + 'x' * 200)
        assert rv.status_code == 400


# ----------------------------------------------------------------
# Error pages
# ----------------------------------------------------------------

class TestErrorPages:
    def test_404_returns_html(self, client):
        rv = client.get('/this-route-does-not-exist')
        assert rv.status_code == 404
