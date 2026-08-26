"""
test_seo.py — SEO and technical SEO tests.

Covers robots.txt, sitemap.xml, landing pages, meta tags, JSON-LD, and noindex on error pages.
No real network requests or downloads are made.
"""
import pytest
import xml.etree.ElementTree as ET
from app import app, SITE_URL


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ----------------------------------------------------------------
# robots.txt
# ----------------------------------------------------------------

class TestRobotsTxt:
    def test_returns_200(self, client):
        rv = client.get('/robots.txt')
        assert rv.status_code == 200

    def test_content_type_is_plain(self, client):
        rv = client.get('/robots.txt')
        assert rv.content_type.startswith('text/plain')

    def test_contains_user_agent(self, client):
        body = client.get('/robots.txt').get_data(as_text=True)
        assert 'User-agent: *' in body

    def test_contains_allow_root(self, client):
        body = client.get('/robots.txt').get_data(as_text=True)
        assert 'Allow: /' in body

    def test_disallows_api(self, client):
        body = client.get('/robots.txt').get_data(as_text=True)
        assert 'Disallow: /api/' in body

    def test_disallows_download(self, client):
        body = client.get('/robots.txt').get_data(as_text=True)
        assert 'Disallow: /download/' in body

    def test_contains_sitemap_url(self, client):
        body = client.get('/robots.txt').get_data(as_text=True)
        assert f'Sitemap: {SITE_URL}/sitemap.xml' in body


# ----------------------------------------------------------------
# sitemap.xml
# ----------------------------------------------------------------

class TestSitemapXml:
    def test_returns_200(self, client):
        rv = client.get('/sitemap.xml')
        assert rv.status_code == 200

    def test_content_type_is_xml(self, client):
        rv = client.get('/sitemap.xml')
        assert 'xml' in rv.content_type

    def test_is_valid_xml(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        ET.fromstring(body)  # raises if invalid

    def test_contains_urlset(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert '<urlset' in body

    def test_lists_homepage(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert f'{SITE_URL}/' in body

    def test_lists_video_landing_page(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert f'{SITE_URL}/youtube-video-downloader' in body

    def test_lists_audio_landing_page(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert f'{SITE_URL}/youtube-audio-downloader' in body

    def test_excludes_api_routes(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert '/api/' not in body

    def test_excludes_download_routes(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert '/download/' not in body

    def test_three_urls_total(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        assert body.count('<url>') == 3

    def test_all_urls_have_loc(self, client):
        body = client.get('/sitemap.xml').get_data(as_text=True)
        root = ET.fromstring(body)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = root.findall('sm:url', ns)
        for url in urls:
            loc = url.find('sm:loc', ns)
            assert loc is not None and loc.text, "Each <url> must have a <loc>"


# ----------------------------------------------------------------
# Homepage SEO
# ----------------------------------------------------------------

class TestHomepageSEO:
    def test_has_title_tag(self, client):
        body = client.get('/').get_data(as_text=True)
        assert '<title>' in body
        assert '</title>' in body

    def test_has_meta_description(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'meta name="description"' in body

    def test_has_canonical_link(self, client):
        body = client.get('/').get_data(as_text=True)
        assert '<link rel="canonical"' in body
        assert SITE_URL in body

    def test_has_og_title(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'og:title' in body

    def test_has_og_description(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'og:description' in body

    def test_has_og_url(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'og:url' in body

    def test_has_twitter_card(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'twitter:card' in body

    def test_has_json_ld(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'application/ld+json' in body
        assert 'WebApplication' in body

    def test_has_robots_meta_index(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'name="robots"' in body
        assert 'index' in body

    def test_has_theme_color(self, client):
        body = client.get('/').get_data(as_text=True)
        assert 'theme-color' in body

    def test_status_200(self, client):
        assert client.get('/').status_code == 200

    def test_footer_links(self, client):
        body = client.get('/').get_data(as_text=True)
        assert '/youtube-video-downloader' in body
        assert '/youtube-audio-downloader' in body
        assert '/sitemap.xml' in body


# ----------------------------------------------------------------
# Landing pages
# ----------------------------------------------------------------

class TestLandingPages:
    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_returns_200(self, client, path):
        assert client.get(path).status_code == 200

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_title(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert '<title>' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_meta_description(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'meta name="description"' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_canonical(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert '<link rel="canonical"' in body
        assert SITE_URL in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_json_ld(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'application/ld+json' in body
        assert 'WebApplication' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_og_tags(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'og:title' in body
        assert 'og:description' in body
        assert 'og:url' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_twitter_card(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'twitter:card' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_robots_index(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'name="robots"' in body
        assert 'index' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_faq_section(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'Frequently Asked Questions' in body

    @pytest.mark.parametrize("path", [
        '/youtube-video-downloader',
        '/youtube-audio-downloader',
    ])
    def test_has_footer_nav(self, client, path):
        body = client.get(path).get_data(as_text=True)
        assert 'role="contentinfo"' in body

    def test_video_landing_has_correct_title(self, client):
        body = client.get('/youtube-video-downloader').get_data(as_text=True)
        assert 'YouTube Video Downloader' in body

    def test_audio_landing_has_correct_title(self, client):
        body = client.get('/youtube-audio-downloader').get_data(as_text=True)
        assert 'YouTube Audio Downloader' in body

    def test_video_landing_contains_howto_content(self, client):
        body = client.get('/youtube-video-downloader').get_data(as_text=True)
        assert 'How to Download YouTube Videos' in body

    def test_audio_landing_contains_conversion_content(self, client):
        body = client.get('/youtube-audio-downloader').get_data(as_text=True)
        assert 'Convert YouTube to MP3' in body

    def test_video_landing_links_to_audio(self, client):
        body = client.get('/youtube-video-downloader').get_data(as_text=True)
        assert '/youtube-audio-downloader' in body

    def test_audio_landing_links_to_video(self, client):
        body = client.get('/youtube-audio-downloader').get_data(as_text=True)
        assert '/youtube-video-downloader' in body


# ----------------------------------------------------------------
# Error pages — noindex
# ----------------------------------------------------------------

class TestErrorPageSEO:
    def test_404_has_noindex(self, client):
        rv = client.get('/this-does-not-exist')
        assert rv.status_code == 404
        body = rv.get_data(as_text=True)
        assert 'noindex' in body

    def test_404_has_title(self, client):
        body = client.get('/this-does-not-exist').get_data(as_text=True)
        assert '<title>' in body
        assert 'Error' in body


# ----------------------------------------------------------------
# API routes excluded from visible pages
# ----------------------------------------------------------------

class TestApiExclusions:
    def test_download_route_returns_404_for_missing_job(self, client):
        rv = client.get('/download/nonexistent')
        assert rv.status_code == 404

    def test_info_requires_post(self, client):
        rv = client.get('/api/info')
        assert rv.status_code == 405

    def test_progress_requires_get(self, client):
        rv = client.post('/api/progress/test-id')
        assert rv.status_code == 405
