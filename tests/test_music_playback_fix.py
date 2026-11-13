"""
Unit & Integration Tests for DRM-enabled Persistent Chrome Web Music Streaming.
Verifies system Chrome binary channel, audio autoplay bypass flags, persistent user data profile,
ARIA/selector/keyboard fallback hierarchy, and URL dispatching across Spotify, YouTube Music, and SoundCloud.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.browser import BrowserEngine


@pytest.mark.asyncio
async def test_play_web_music_chrome_persistent_launch():
    """Verify play_web_music launches with persistent context, system Chrome channel, and DRM/audio flags."""
    engine = BrowserEngine(headless=False)
    
    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.bring_to_front = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    fake_page.title = AsyncMock(return_value="Spotify - Search Results")
    
    # Mock locator for play button
    mock_locator = MagicMock()
    mock_locator.first = mock_locator
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.click = AsyncMock()
    mock_locator.element_handle = AsyncMock(return_value=MagicMock())
    
    fake_page.locator = MagicMock(return_value=mock_locator)
    fake_page.get_by_role = MagicMock(return_value=mock_locator)

    fake_context = MagicMock()
    fake_context.pages = [fake_page]
    fake_context.close = AsyncMock()

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=fake_context)
    mock_pw.stop = AsyncMock()

    with patch("app.tools.browser.async_playwright") as mock_pw_factory:
        mock_factory_cm = MagicMock()
        mock_factory_cm.start = AsyncMock(return_value=mock_pw)
        mock_pw_factory.return_value = mock_factory_cm

        res = await engine.play_web_music(service="spotify", query="Coldplay Yellow")

        assert res["status"] == "success"
        assert res["service"] == "spotify"
        assert "open.spotify.com/search/Coldplay+Yellow" in res["url"]
        assert "chrome_spotify_profile" in res["profile_dir"]

        # Verify launch parameters passed to Playwright
        mock_pw.chromium.launch_persistent_context.assert_called_once()
        call_kwargs = mock_pw.chromium.launch_persistent_context.call_args[1]
        assert call_kwargs["channel"] == "chrome"
        assert "--autoplay-policy=no-user-gesture-required" in call_kwargs["args"]
        assert "--enable-features=AudioServiceOutOfProcess" in call_kwargs["args"]
        assert call_kwargs["ignore_default_args"] == ["--disable-component-update"]
        assert "chrome_spotify_profile" in call_kwargs["user_data_dir"]


@pytest.mark.asyncio
async def test_play_web_music_services_routing():
    """Verify correct URL formulation for YouTube Music, SoundCloud, and Spotify."""
    engine = BrowserEngine(headless=True)
    
    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.bring_to_front = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    fake_page.title = AsyncMock(return_value="YT Music")
    
    mock_locator = MagicMock()
    mock_locator.first = mock_locator
    mock_locator.is_visible = AsyncMock(return_value=False)
    fake_page.locator = MagicMock(return_value=mock_locator)
    fake_page.get_by_role = MagicMock(return_value=mock_locator)

    fake_context = MagicMock()
    fake_context.pages = [fake_page]

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=fake_context)
    mock_pw.stop = AsyncMock()

    with patch("app.tools.browser.async_playwright") as mock_pw_factory:
        mock_factory_cm = MagicMock()
        mock_factory_cm.start = AsyncMock(return_value=mock_pw)
        mock_pw_factory.return_value = mock_factory_cm

        # 1. YouTube Music
        res_yt = await engine.play_web_music(service="ytmusic", query="Interstellar Hans Zimmer")
        assert res_yt["status"] == "success"
        assert "music.youtube.com/search?q=Interstellar+Hans+Zimmer" in res_yt["url"]

        # 2. SoundCloud
        res_sc = await engine.play_web_music(service="soundcloud", query="Synthwave Radio")
        assert res_sc["status"] == "success"
        assert "soundcloud.com/search?q=Synthwave+Radio" in res_sc["url"]


@pytest.mark.asyncio
async def test_play_web_music_selector_fallback():
    """Verify fallback mechanism through ARIA role to selector and keyboard press."""
    engine = BrowserEngine(headless=True)
    
    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.bring_to_front = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    fake_page.title = AsyncMock(return_value="Playing Track")
    fake_page.keyboard.press = AsyncMock()

    # Fail ARIA button, succeed on keyboard fallback
    mock_aria = MagicMock()
    mock_aria.first = mock_aria
    mock_aria.is_visible = AsyncMock(return_value=False)
    fake_page.get_by_role = MagicMock(return_value=mock_aria)

    mock_track = MagicMock()
    mock_track.first = mock_track
    mock_track.is_visible = AsyncMock(return_value=True)
    mock_track.focus = AsyncMock()
    fake_page.locator = MagicMock(return_value=mock_track)

    fake_context = MagicMock()
    fake_context.pages = [fake_page]

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=fake_context)
    mock_pw.stop = AsyncMock()

    with patch("app.tools.browser.async_playwright") as mock_pw_factory:
        mock_factory_cm = MagicMock()
        mock_factory_cm.start = AsyncMock(return_value=mock_pw)
        mock_pw_factory.return_value = mock_factory_cm

        res = await engine.play_web_music(service="spotify", query="Billie Eilish Birds of a Feather")
        assert res["status"] == "success"
        mock_track.focus.assert_called_once()
        fake_page.keyboard.press.assert_called_with("Enter")

