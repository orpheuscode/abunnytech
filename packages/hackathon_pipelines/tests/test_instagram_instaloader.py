from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from hackathon_pipelines.adapters.instagram_instaloader import (
    InstagramInstaloaderConfig,
    InstagramInstaloaderDownloader,
    extract_shortcode_from_instagram_url,
)


def test_extract_shortcode_from_instagram_url_supports_reel_paths() -> None:
    assert extract_shortcode_from_instagram_url("https://www.instagram.com/reels/ABC123/") == "ABC123"
    assert extract_shortcode_from_instagram_url("https://www.instagram.com/reel/XYZ789/?igsh=1") == "XYZ789"


def test_extract_shortcode_from_instagram_url_rejects_non_reel_paths() -> None:
    with pytest.raises(ValueError):
        extract_shortcode_from_instagram_url("https://www.instagram.com/explore/")


@pytest.mark.asyncio
async def test_instaloader_downloader_downloads_mp4_and_normalizes_metadata(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakePost:
        def __init__(self, shortcode: str) -> None:
            self.shortcode = shortcode
            self.is_video = True
            self.video_url = f"https://cdn.example.com/{shortcode}.mp4"
            self.owner_username = "creator_test"
            self.caption = "Great product demo"
            self.likes = 2345
            self.comments = 67

        @staticmethod
        def from_shortcode(context: object, shortcode: str) -> FakePost:
            captured["from_shortcode_context"] = context
            captured["shortcode"] = shortcode
            return FakePost(shortcode)

    class FakeInstaloader:
        def __init__(self, **kwargs: object) -> None:
            captured["loader_kwargs"] = kwargs
            self.context = object()

        def download_post(self, post: FakePost, target: str) -> bool:
            captured["download_target"] = target
            dirname_pattern = str(captured["loader_kwargs"]["dirname_pattern"])
            target_dir = Path(dirname_pattern.replace("{target}", target))
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / f"{post.shortcode}.mp4").write_bytes(b"fake-mp4")
            return True

    downloader = InstagramInstaloaderDownloader(
        config=InstagramInstaloaderConfig(download_dir=tmp_path),
        instaloader_module=SimpleNamespace(Instaloader=FakeInstaloader, Post=FakePost),
    )

    result = await downloader.download_reel(
        source_url="https://www.instagram.com/reels/ABC123/",
        reel_id="ABC123",
    )

    assert result.shortcode == "ABC123"
    assert result.media_url == "https://cdn.example.com/ABC123.mp4"
    assert result.creator_handle == "creator_test"
    assert result.caption_text == "Great product demo"
    assert result.likes == 2345
    assert result.comments == 67
    assert Path(result.local_video_path).exists()
    assert captured["download_target"] == "ABC123"


def test_instaloader_downloader_can_authenticate_from_browser_cookies(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    cookie_file = tmp_path / "Cookies"
    cookie_file.write_text("stub", encoding="utf-8")
    key_file = tmp_path / "Local State"
    key_file.write_text("{}", encoding="utf-8")

    class FakePost:
        def __init__(self, shortcode: str) -> None:
            self.shortcode = shortcode
            self.is_video = True
            self.video_url = f"https://cdn.example.com/{shortcode}.mp4"
            self.owner_username = "creator_test"
            self.caption = "Great product demo"
            self.likes = 2345
            self.comments = 67

        @staticmethod
        def from_shortcode(context: object, shortcode: str) -> FakePost:
            return FakePost(shortcode)

    class FakeSessionCookies:
        def update(self, cookie_jar: object) -> None:
            captured["cookie_jar"] = cookie_jar

    class FakeSession:
        def __init__(self) -> None:
            self.cookies = FakeSessionCookies()
            self.headers = {}

        def get(self, url: str):
            captured["homepage_url"] = url
            return SimpleNamespace(raise_for_status=lambda: None)

    class FakeContext:
        def __init__(self) -> None:
            self._session = FakeSession()
            self.username: str | None = None

    class FakeInstaloader:
        def __init__(self, **kwargs: object) -> None:
            self.context = FakeContext()

        def test_login(self) -> str | None:
            return "instagram_test"

        def download_post(self, post: FakePost, target: str) -> bool:
            target_dir = tmp_path / target
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / f"{post.shortcode}.mp4").write_bytes(b"fake-mp4")
            return True

    class FakeBrowserCookieModule:
        @staticmethod
        def chrome(
            *,
            cookie_file: str | None = None,
            domain_name: str = "",
            key_file: str | None = None,
        ) -> object:
            captured["cookie_file"] = cookie_file
            captured["domain_name"] = domain_name
            captured["key_file"] = key_file
            return {"sessionid": "abc123"}

    downloader = InstagramInstaloaderDownloader(
        config=InstagramInstaloaderConfig(
            download_dir=tmp_path,
            browser_name="chrome",
            browser_cookie_file=cookie_file,
            browser_key_file=key_file,
        ),
        instaloader_module=SimpleNamespace(Instaloader=FakeInstaloader, Post=FakePost),
        browser_cookie_module=FakeBrowserCookieModule(),
    )

    result = downloader._download_reel_sync(
        source_url="https://www.instagram.com/reels/ABC123/",
        reel_id="ABC123",
    )

    assert result.shortcode == "ABC123"
    assert captured["cookie_file"] == str(cookie_file)
    assert captured["domain_name"] == "instagram.com"
    assert captured["key_file"] == str(key_file)
    assert captured["cookie_jar"] == {"sessionid": "abc123"}
    assert captured["homepage_url"] == "https://www.instagram.com/"
    assert downloader._config.browser_cookie_file == cookie_file


def test_instaloader_cookie_auth_primes_csrf_header(tmp_path: Path) -> None:
    cookie_file = tmp_path / "Cookies"
    cookie_file.write_text("stub", encoding="utf-8")

    class FakeCookieJar(dict):
        pass

    class FakeCookies:
        def __init__(self) -> None:
            self.updated_with = None

        def update(self, cookie_jar: object) -> None:
            self.updated_with = cookie_jar

        def get_dict(self) -> dict[str, str]:
            return {"csrftoken": "csrf_from_session"}

    class FakeSession:
        def __init__(self) -> None:
            self.cookies = FakeCookies()
            self.headers: dict[str, str] = {}

        def get(self, url: str):
            return SimpleNamespace(raise_for_status=lambda: None)

    class FakeContext:
        def __init__(self) -> None:
            self._session = FakeSession()
            self.username: str | None = None

    class FakeInstaloader:
        def __init__(self, **kwargs: object) -> None:
            self.context = FakeContext()

        def test_login(self) -> str | None:
            return "instagram_test"

    class FakeBrowserCookieModule:
        @staticmethod
        def chrome(**kwargs) -> object:
            return FakeCookieJar({"csrftoken": "csrf_from_cookie", "sessionid": "session123"})

    downloader = InstagramInstaloaderDownloader(
        config=InstagramInstaloaderConfig(
            download_dir=tmp_path,
            browser_name="chrome",
            browser_cookie_file=cookie_file,
        ),
        instaloader_module=SimpleNamespace(Instaloader=FakeInstaloader),
        browser_cookie_module=FakeBrowserCookieModule(),
    )

    loader = downloader._build_loader()
    downloader._load_browser_cookies(loader)

    assert loader.context._session.headers["Referer"] == "https://www.instagram.com/"
    assert loader.context._session.headers["X-CSRFToken"] == "csrf_from_session"


def test_instaloader_from_runtime_env_prefers_network_cookie_db_and_local_state(tmp_path: Path) -> None:
    profile_dir = tmp_path / "Profile 9"
    network_cookie_file = profile_dir / "Network" / "Cookies"
    network_cookie_file.parent.mkdir(parents=True, exist_ok=True)
    network_cookie_file.write_text("stub", encoding="utf-8")
    local_state = tmp_path / "Local State"
    local_state.write_text("{}", encoding="utf-8")

    config = InstagramInstaloaderDownloader.from_runtime_env(
        {
            "CHROME_USER_DATA_DIR": str(tmp_path),
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
        }
    )

    assert config.browser_cookie_file == network_cookie_file
    assert config.browser_key_file == local_state


@pytest.mark.asyncio
async def test_instaloader_downloader_uses_authenticated_session_video_candidates(tmp_path: Path) -> None:
    class FakePost:
        def __init__(self, shortcode: str) -> None:
            self.shortcode = shortcode
            self.is_video = True
            self.owner_username = "creator_test"
            self.caption = "Great product demo"
            self.likes = 2345
            self.comments = 67
            self.date_local = datetime(2026, 4, 5, 6, 17, 26)

        @staticmethod
        def from_shortcode(context: object, shortcode: str) -> FakePost:
            return FakePost(shortcode)

        def _field(self, name: str) -> str:
            if name != "video_url":
                raise KeyError(name)
            return "https://cdn.example.com/primary.mp4?x=1"

    class FakeResponse:
        def __init__(self, body: bytes, content_type: str = "video/mp4") -> None:
            self.status_code = 200
            self.headers = {"Content-Type": content_type}
            self.raw = SimpleNamespace(read=lambda *args, **kwargs: body, decode_content=False)

        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        def get(self, url: str, *, stream: bool = False, headers: dict[str, str] | None = None):
            assert stream is True
            assert headers == {
                "Referer": "https://www.instagram.com/reels/ABC123/",
                "Origin": "https://www.instagram.com",
            }
            return FakeResponse(b"fake-mp4")

    class FakeContext:
        def __init__(self) -> None:
            self._session = FakeSession()

        def write_raw(self, resp: object, filename: str) -> None:
            Path(filename).write_bytes(b"fake-mp4")

    class FakeInstaloader:
        def __init__(self, **kwargs: object) -> None:
            self.context = FakeContext()

        def download_post(self, post: FakePost, target: str) -> bool:
            raise AssertionError("download_post should not be used when session download succeeds")

    downloader = InstagramInstaloaderDownloader(
        config=InstagramInstaloaderConfig(download_dir=tmp_path),
        instaloader_module=SimpleNamespace(Instaloader=FakeInstaloader, Post=FakePost),
    )

    result = await downloader.download_reel(
        source_url="https://www.instagram.com/reels/ABC123/",
        reel_id="ABC123",
    )

    assert result.media_url == "https://cdn.example.com/primary.mp4?x=1"
    assert Path(result.local_video_path).exists()


@pytest.mark.asyncio
async def test_instaloader_downloader_falls_through_bad_video_candidates(tmp_path: Path) -> None:
    requests: list[str] = []

    class FakePost:
        def __init__(self, shortcode: str) -> None:
            self.shortcode = shortcode
            self.is_video = True
            self.owner_username = "creator_test"
            self.caption = "Great product demo"
            self.likes = 2345
            self.comments = 67
            self.date_local = datetime(2026, 4, 5, 6, 17, 26)
            self._context = SimpleNamespace(iphone_support=True, is_logged_in=True)
            self._iphone_struct = {
                "video_versions": [
                    {"url": "https://cdn.example.com/bad.mp4?x=1"},
                    {"url": "https://cdn.example.com/good.mp4?x=1"},
                ]
            }

        @staticmethod
        def from_shortcode(context: object, shortcode: str) -> FakePost:
            return FakePost(shortcode)

        def _field(self, name: str) -> str:
            if name != "video_url":
                raise KeyError(name)
            return "https://cdn.example.com/bad.mp4?x=1"

        @property
        def video_url(self) -> str:
            raise AssertionError("video_url property should not be consulted for candidate selection")

    class FakeResponse:
        def __init__(self, *, status_code: int, body: bytes = b"", content_type: str = "video/mp4") -> None:
            self.status_code = status_code
            self.headers = {"Content-Type": content_type}
            self.raw = SimpleNamespace(read=lambda *args, **kwargs: body, decode_content=False)

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    class FakeSession:
        def get(self, url: str, *, stream: bool = False, headers: dict[str, str] | None = None):
            requests.append(url)
            if "bad.mp4" in url:
                return FakeResponse(status_code=400)
            return FakeResponse(status_code=200, body=b"good-mp4")

    class FakeContext:
        def __init__(self) -> None:
            self._session = FakeSession()

        def write_raw(self, resp: object, filename: str) -> None:
            Path(filename).write_bytes(b"good-mp4")

    class FakeInstaloader:
        def __init__(self, **kwargs: object) -> None:
            self.context = FakeContext()

        def download_post(self, post: FakePost, target: str) -> bool:
            raise AssertionError("download_post should not be used when a later candidate succeeds")

    downloader = InstagramInstaloaderDownloader(
        config=InstagramInstaloaderConfig(download_dir=tmp_path),
        instaloader_module=SimpleNamespace(Instaloader=FakeInstaloader, Post=FakePost),
    )

    result = await downloader.download_reel(
        source_url="https://www.instagram.com/reels/ABC123/",
        reel_id="ABC123",
    )

    assert requests == [
        "https://cdn.example.com/bad.mp4?x=1",
        "https://cdn.example.com/good.mp4?x=1",
    ]
    assert result.media_url == "https://cdn.example.com/good.mp4?x=1"
    assert Path(result.local_video_path).exists()
