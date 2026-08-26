"""
test_utils.py — Unit tests for utils.py

These tests do NOT make real network requests or YouTube downloads.
"""
import pytest
from utils import is_valid_url, sanitize_filename, check_ffmpeg


class TestIsValidUrl:
    def test_youtube_long_url(self):
        assert is_valid_url("https://youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_youtu_be_short_url(self):
        assert is_valid_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_youtube_www(self):
        assert is_valid_url("https://www.youtube.com/watch?v=abc123") is True

    def test_prefixed_youtube_url(self):
        assert is_valid_url("1 = https://youtu.be/dQw4w9WgXcQ") is True

    def test_prefixed_youtube_watch_url(self):
        assert is_valid_url("2 = https://www.youtube.com/watch?v=KUrm-F8mXJQ&list=PLTDARY42LDV7WGmlzZtY-w9pemyPrKNUZ&index=4") is True

    def test_vimeo(self):
        assert is_valid_url("https://vimeo.com/12345678") is True

    def test_twitter(self):
        assert is_valid_url("https://twitter.com/user/status/123") is True

    def test_x_com(self):
        assert is_valid_url("https://x.com/user/status/123") is True

    def test_soundcloud(self):
        assert is_valid_url("https://soundcloud.com/artist/track") is True

    def test_empty_string(self):
        assert is_valid_url("") is False

    def test_plain_text(self):
        assert is_valid_url("not a url") is False

    def test_unsupported_domain(self):
        assert is_valid_url("https://example.com/video") is False

    def test_no_scheme(self):
        assert is_valid_url("youtube.com/watch?v=abc") is False

    def test_malformed(self):
        assert is_valid_url("http://") is False

    def test_very_long_url(self):
        # Should return False or True (supported domain check), not raise
        long_url = "https://youtube.com/" + "a" * 3000
        result = is_valid_url(long_url)
        assert isinstance(result, bool)


class TestSanitizeFilename:
    def test_normal_name(self):
        assert sanitize_filename("Normal File Name") == "Normal File Name"

    def test_removes_forward_slash(self):
        assert sanitize_filename("File/With/Slashes") == "FileWithSlashes"

    def test_removes_colons(self):
        assert sanitize_filename("File:With:Colons") == "FileWithColons"

    def test_removes_asterisk(self):
        assert sanitize_filename("File*Name") == "FileName"

    def test_removes_question_mark(self):
        assert sanitize_filename("File?Name") == "FileName"

    def test_removes_double_quote(self):
        assert sanitize_filename('File"Name') == "FileName"

    def test_removes_angle_brackets(self):
        assert sanitize_filename("File<>Name") == "FileName"

    def test_removes_pipe(self):
        assert sanitize_filename("File|Name") == "FileName"

    def test_empty_string_returns_default(self):
        assert sanitize_filename("") == "download"

    def test_only_invalid_chars_returns_default(self):
        assert sanitize_filename(":::***") == "download"

    def test_strips_whitespace(self):
        assert sanitize_filename("  My Video  ") == "My Video"


class TestCheckFfmpeg:
    def test_returns_bool(self):
        result = check_ffmpeg()
        assert isinstance(result, bool)
