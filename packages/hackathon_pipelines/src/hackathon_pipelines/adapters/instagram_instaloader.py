"""Instaloader-backed reel downloader used after Browser Use discovery."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from packages.shared.browser_runtime_config import (
    ENV_CHROME_PROFILE_DIRECTORY,
    ENV_CHROME_USER_DATA_DIR,
    build_effective_browser_runtime_env,
)
from pydantic import BaseModel, ConfigDict, Field


class InstagramInstaloaderConfig(BaseModel):
    """Configuration for downloading public Instagram reels through Instaloader."""

    model_config = ConfigDict(extra="forbid")

    download_dir: Path
    username: str | None = None
    password: str | None = None
    sessionfile: str | None = None
    browser_name: str | None = None
    browser_cookie_file: Path | None = None
    browser_key_file: Path | None = None
    browser_cookie_domain: str = "instagram.com"
    quiet: bool = True
    request_timeout: float = Field(default=120.0, ge=1.0)
    max_connection_attempts: int = Field(default=3, ge=1)


class InstagramInstaloaderDownload(BaseModel):
    """Normalized result returned after Instaloader downloads a reel."""

    model_config = ConfigDict(extra="forbid")

    reel_id: str
    source_url: str
    shortcode: str
    local_video_path: str
    media_url: str | None = None
    creator_handle: str | None = None
    caption_text: str | None = None
    likes: int | None = None
    comments: int | None = None


def extract_shortcode_from_instagram_url(source_url: str) -> str:
    """Extract a reel/post shortcode from a canonical Instagram URL."""

    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] not in {"reel", "reels", "p", "tv"}:
        msg = f"Unsupported Instagram reel URL: {source_url}"
        raise ValueError(msg)
    return parts[1]


def _infer_media_suffix(media_url: str, content_type: str | None = None) -> str:
    """Infer a stable file suffix for a downloaded reel video."""

    parsed_path = Path(urlparse(media_url).path)
    if parsed_path.suffix:
        return parsed_path.suffix.lower()
    if content_type:
        normalized = content_type.split(";", 1)[0].strip().lower()
        if normalized == "video/mp4":
            return ".mp4"
        if "/" in normalized:
            return f".{normalized.rsplit('/', 1)[-1]}"
    return ".mp4"


class InstagramInstaloaderDownloader:
    """Download queued reels by shortcode using Instaloader, not the browser."""

    def __init__(
        self,
        *,
        config: InstagramInstaloaderConfig | None = None,
        instaloader_module: Any | None = None,
        browser_cookie_module: Any | None = None,
    ) -> None:
        self._config = config or self.from_env()
        self._instaloader_module = instaloader_module
        self._browser_cookie_module = browser_cookie_module

    @staticmethod
    def from_env() -> InstagramInstaloaderConfig:
        return InstagramInstaloaderDownloader.from_runtime_env()

    @staticmethod
    def from_runtime_env(
        browser_runtime_env: Mapping[str, str] | None = None,
    ) -> InstagramInstaloaderConfig:
        runtime_env = build_effective_browser_runtime_env(environ=browser_runtime_env or os.environ)
        chrome_user_data_dir = Path(
            runtime_env.get(ENV_CHROME_USER_DATA_DIR, "~/.config/google-chrome")
        ).expanduser()
        chrome_profile_directory = runtime_env.get(ENV_CHROME_PROFILE_DIRECTORY, "Default").strip() or "Default"
        default_cookie_file = _default_cookie_file(chrome_user_data_dir, chrome_profile_directory)
        default_key_file = _default_key_file(chrome_user_data_dir)
        return InstagramInstaloaderConfig(
            download_dir=Path(os.getenv("REEL_TEMP_VIDEO_DIR", "data/tmp_reels_instaloader")),
            username=os.getenv("INSTALOADER_USERNAME") or None,
            password=os.getenv("INSTALOADER_PASSWORD") or None,
            sessionfile=os.getenv("INSTALOADER_SESSIONFILE") or None,
            browser_name=os.getenv("INSTALOADER_BROWSER_NAME", "chrome").strip().lower() or None,
            browser_cookie_file=Path(os.getenv("INSTALOADER_COOKIE_FILE")).expanduser()
            if os.getenv("INSTALOADER_COOKIE_FILE")
            else default_cookie_file,
            browser_key_file=Path(os.getenv("INSTALOADER_COOKIE_KEY_FILE")).expanduser()
            if os.getenv("INSTALOADER_COOKIE_KEY_FILE")
            else default_key_file,
            browser_cookie_domain=os.getenv("INSTALOADER_COOKIE_DOMAIN", "instagram.com"),
            request_timeout=float(os.getenv("INSTALOADER_REQUEST_TIMEOUT_SECONDS", "120")),
            max_connection_attempts=int(os.getenv("INSTALOADER_MAX_CONNECTION_ATTEMPTS", "3")),
        )

    def _module(self) -> Any:
        if self._instaloader_module is not None:
            return self._instaloader_module
        import instaloader

        self._instaloader_module = instaloader
        return instaloader

    def _cookie_module(self) -> Any:
        if self._browser_cookie_module is not None:
            return self._browser_cookie_module
        import browser_cookie3

        self._browser_cookie_module = browser_cookie3
        return browser_cookie3

    def _build_loader(self) -> Any:
        self._config.download_dir.mkdir(parents=True, exist_ok=True)
        module = self._module()
        return module.Instaloader(
            sleep=False,
            quiet=self._config.quiet,
            dirname_pattern=str(self._config.download_dir / "{target}"),
            filename_pattern="{shortcode}",
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            max_connection_attempts=self._config.max_connection_attempts,
            request_timeout=self._config.request_timeout,
        )

    def _authenticate_if_configured(self, loader: Any) -> None:
        if self._config.username and self._config.sessionfile:
            loader.load_session_from_file(self._config.username, self._config.sessionfile)
            return
        if self._config.username and self._config.password:
            loader.login(self._config.username, self._config.password)
            return
        if self._config.browser_name:
            self._load_browser_cookies(loader)

    def _load_browser_cookies(self, loader: Any) -> None:
        cookie_file = self._config.browser_cookie_file
        if cookie_file is not None and not cookie_file.exists():
            msg = f"Configured browser cookie file does not exist: {cookie_file}"
            raise FileNotFoundError(msg)
        key_file = self._config.browser_key_file
        if key_file is not None and not key_file.exists():
            key_file = None

        browser_cookie_module = self._cookie_module()
        browser_name = (self._config.browser_name or "").lower()
        loader_fn = {
            "chrome": getattr(browser_cookie_module, "chrome", None),
            "chromium": getattr(browser_cookie_module, "chromium", None),
            "edge": getattr(browser_cookie_module, "edge", None),
            "brave": getattr(browser_cookie_module, "brave", None),
        }.get(browser_name)
        if loader_fn is None:
            msg = f"Unsupported INSTALOADER_BROWSER_NAME={self._config.browser_name!r}"
            raise RuntimeError(msg)

        try:
            cookie_jar = loader_fn(
                cookie_file=str(cookie_file) if cookie_file is not None else None,
                domain_name=self._config.browser_cookie_domain,
                key_file=str(key_file) if key_file is not None else None,
            )
        except PermissionError as exc:
            msg = (
                "Unable to decrypt Chrome cookies for Instaloader. "
                "This environment may not have access to the desktop keyring or browser profile secrets."
            )
            raise RuntimeError(msg) from exc
        loader.context._session.cookies.update(cookie_jar)
        self._prime_session_headers_from_cookies(loader.context._session, cookie_jar)
        username = self._validate_browser_cookie_login(loader)
        if username is None:
            msg = "Failed to authenticate Instaloader from browser cookies."
            raise RuntimeError(msg)
        loader.context.username = username

    @staticmethod
    def _cookie_value(cookie_jar: object, name: str) -> str | None:
        if isinstance(cookie_jar, dict):
            value = cookie_jar.get(name)
            return str(value) if value else None
        if hasattr(cookie_jar, "get"):
            try:
                value = cookie_jar.get(name)
            except Exception:
                value = None
            if value:
                return str(value)
        if isinstance(cookie_jar, Iterable):
            for cookie in cookie_jar:
                cookie_name = getattr(cookie, "name", None)
                if cookie_name == name:
                    value = getattr(cookie, "value", None)
                    if value:
                        return str(value)
        return None

    @classmethod
    def _prime_session_headers_from_cookies(cls, session: Any, cookie_jar: object) -> None:
        csrf_token = cls._cookie_value(cookie_jar, "csrftoken")
        if not csrf_token and hasattr(session, "cookies"):
            cookies = session.cookies
            if hasattr(cookies, "get_dict"):
                try:
                    csrf_token = cookies.get_dict().get("csrftoken")
                except Exception:
                    csrf_token = None
            elif hasattr(cookies, "get"):
                try:
                    csrf_token = cookies.get("csrftoken")
                except Exception:
                    csrf_token = None
        headers = getattr(session, "headers", None)
        if headers is not None and hasattr(headers, "update"):
            updates = {"Referer": "https://www.instagram.com/"}
            if csrf_token:
                updates["X-CSRFToken"] = str(csrf_token)
            headers.update(updates)

    def _validate_browser_cookie_login(self, loader: Any) -> str | None:
        context = loader.context
        session = context._session
        try:
            homepage = session.get("https://www.instagram.com/")
            if hasattr(homepage, "raise_for_status"):
                homepage.raise_for_status()
        except Exception:
            pass

        self._prime_session_headers_from_cookies(session, getattr(session, "cookies", {}))
        username = loader.test_login()
        if username is not None:
            return username

        self._prime_session_headers_from_cookies(session, getattr(session, "cookies", {}))
        return loader.test_login()

    def _locate_video_path(self, shortcode: str) -> Path:
        target_dir = self._config.download_dir / shortcode
        candidates = sorted(target_dir.glob("*.mp4"))
        if not candidates:
            msg = f"Instaloader did not produce an MP4 file for shortcode {shortcode}"
            raise FileNotFoundError(msg)
        return candidates[0]

    @staticmethod
    def _extract_video_urls(post: Any) -> list[str]:
        candidates: list[str] = []

        field_getter = getattr(post, "_field", None)
        if callable(field_getter):
            try:
                graphql_url = field_getter("video_url")
            except Exception:
                graphql_url = None
            if isinstance(graphql_url, str) and graphql_url.startswith(("http://", "https://")):
                candidates.append(graphql_url)

        context = getattr(post, "_context", None)
        iphone_support = bool(getattr(context, "iphone_support", False))
        is_logged_in = bool(getattr(context, "is_logged_in", False))
        iphone_struct = getattr(post, "_iphone_struct", None)
        if iphone_support and is_logged_in and isinstance(iphone_struct, dict):
            for version in iphone_struct.get("video_versions", []):
                if isinstance(version, dict):
                    version_url = version.get("url")
                    if isinstance(version_url, str) and version_url.startswith(("http://", "https://")):
                        candidates.append(version_url)

        try:
            direct_video_url = getattr(post, "video_url", None)
        except Exception:
            direct_video_url = None
        if isinstance(direct_video_url, str) and direct_video_url.startswith(("http://", "https://")):
            candidates.append(direct_video_url)

        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    @staticmethod
    def _post_datetime(post: Any) -> datetime:
        timestamp = getattr(post, "date_local", None)
        if isinstance(timestamp, datetime):
            return timestamp
        return datetime.now()

    def _download_video_candidate_via_session(
        self,
        *,
        loader: Any,
        shortcode: str,
        source_url: str,
        video_url: str,
        mtime: datetime,
    ) -> Path:
        session = loader.context._session
        response = session.get(
            video_url,
            stream=True,
            headers={
                "Referer": source_url,
                "Origin": "https://www.instagram.com",
            },
        )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            msg = f"HTTP {status_code} while downloading Instagram reel media"
            raise RuntimeError(msg)
        raw = getattr(response, "raw", None)
        if raw is not None:
            raw.decode_content = True

        content_type = None
        headers = getattr(response, "headers", None)
        if isinstance(headers, Mapping):
            content_type = headers.get("Content-Type")
        suffix = _infer_media_suffix(video_url, content_type)

        target_dir = self._config.download_dir / shortcode
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{shortcode}{suffix}"
        if target_path.exists():
            return target_path

        loader.context.write_raw(response, str(target_path))
        os.utime(target_path, (datetime.now().timestamp(), mtime.timestamp()))
        return target_path

    def _download_video_via_session(
        self,
        *,
        loader: Any,
        post: Any,
        shortcode: str,
        source_url: str,
    ) -> tuple[Path, str]:
        video_urls = self._extract_video_urls(post)
        if not video_urls:
            msg = f"Instagram post {shortcode} did not expose a downloadable video URL"
            raise RuntimeError(msg)

        mtime = self._post_datetime(post)
        failures: list[str] = []
        for video_url in video_urls:
            try:
                local_path = self._download_video_candidate_via_session(
                    loader=loader,
                    shortcode=shortcode,
                    source_url=source_url,
                    video_url=video_url,
                    mtime=mtime,
                )
                return local_path, video_url
            except Exception as exc:
                failures.append(f"{video_url}: {exc}")

        msg = "Failed to download Instagram reel video via authenticated session. " + " | ".join(failures)
        raise RuntimeError(msg)

    def _download_reel_sync(self, *, source_url: str, reel_id: str) -> InstagramInstaloaderDownload:
        shortcode = extract_shortcode_from_instagram_url(source_url)
        loader = self._build_loader()
        self._authenticate_if_configured(loader)

        module = self._module()
        post = module.Post.from_shortcode(loader.context, shortcode)
        if not getattr(post, "is_video", False):
            msg = f"Instagram URL did not resolve to a video reel: {source_url}"
            raise RuntimeError(msg)

        media_url: str | None = None
        try:
            local_path, media_url = self._download_video_via_session(
                loader=loader,
                post=post,
                shortcode=shortcode,
                source_url=source_url,
            )
        except Exception:
            loader.download_post(post, target=shortcode)
            local_path = self._locate_video_path(shortcode)
            media_url = next(iter(self._extract_video_urls(post)), None)

        return InstagramInstaloaderDownload(
            reel_id=reel_id,
            source_url=source_url,
            shortcode=shortcode,
            local_video_path=str(local_path),
            media_url=media_url,
            creator_handle=getattr(post, "owner_username", None),
            caption_text=getattr(post, "caption", None),
            likes=getattr(post, "likes", None),
            comments=getattr(post, "comments", None),
        )

    async def download_reel(self, *, source_url: str, reel_id: str) -> InstagramInstaloaderDownload:
        return await asyncio.to_thread(self._download_reel_sync, source_url=source_url, reel_id=reel_id)


def _default_cookie_file(chrome_user_data_dir: Path, chrome_profile_directory: str) -> Path:
    candidates = (
        chrome_user_data_dir / chrome_profile_directory / "Network" / "Cookies",
        chrome_user_data_dir / chrome_profile_directory / "Cookies",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _default_key_file(chrome_user_data_dir: Path) -> Path | None:
    candidate = chrome_user_data_dir / "Local State"
    return candidate if candidate.exists() else None
