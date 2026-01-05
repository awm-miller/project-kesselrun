"""
Instagram Scraper with Video and Story Support
"""
import os
import logging
import shutil
import random
import time
import http.cookiejar
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional

import instaloader
import asyncio
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

from config import (
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    TEMP_DIR,
    COOKIES_FILE,
    STORY_DELAY_MIN,
    STORY_DELAY_MAX,
)

logger = logging.getLogger("scraper")


@dataclass
class InstagramPost:
    """Represents an Instagram post (image, video, or story)"""
    shortcode: str
    url: str
    caption: str
    date: datetime
    likes: int
    is_video: bool
    is_story: bool = False
    media_path: Optional[Path] = None
    video_url: Optional[str] = None
    screenshot_path: Optional[Path] = None
    

@dataclass
class InstagramProfile:
    """Profile metadata"""
    username: str
    full_name: str
    bio: str
    followers: int
    following: int
    post_count: int


@dataclass
class ScrapeResult:
    """Complete scrape result for an account"""
    profile: InstagramProfile
    posts: List[InstagramPost] = field(default_factory=list)
    stories: List[InstagramPost] = field(default_factory=list)
    error: Optional[str] = None


class InstagramScraper:
    """Scrapes Instagram profiles including videos and stories"""
    
    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self._logged_in = False
        self.download_dir = Path(TEMP_DIR)
        
    def login(self) -> bool:
        """Login to Instagram (required for stories)"""
        # Try cookie-based auth first
        cookies_path = Path(COOKIES_FILE)
        if cookies_path.exists():
            try:
                self._load_cookies(cookies_path)
                self._logged_in = True
                logger.info(f"Logged in via cookies from {COOKIES_FILE}")
                return True
            except Exception as e:
                logger.warning(f"Cookie login failed: {e}")
        
        # Fall back to username/password
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            try:
                self.loader.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                self._logged_in = True
                logger.info(f"Logged in as {INSTAGRAM_USERNAME}")
                return True
            except Exception as e:
                logger.error(f"Login failed: {e}")
                return False
        
        logger.warning("No authentication configured - stories will be skipped")
        return False
    
    def _load_cookies(self, cookies_path: Path):
        """Load cookies from Netscape format cookies.txt file using Firefox import"""
        import http.cookiejar
        
        cookie_jar = http.cookiejar.MozillaCookieJar(str(cookies_path))
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        
        # Extract sessionid and csrftoken for Instaloader
        sessionid = None
        for cookie in cookie_jar:
            if cookie.name == 'sessionid' and 'instagram' in cookie.domain:
                sessionid = cookie.value
                break
        
        if not sessionid:
            raise ValueError("No sessionid found in cookies")
        
        # Use Instaloader's import mechanism
        # We need to set cookies on the context properly
        session = self.loader.context._session
        
        for cookie in cookie_jar:
            if 'instagram' in cookie.domain:
                session.cookies.set_cookie(cookie)
        
        # Set required headers
        session.headers.update({
            'X-IG-App-ID': '936619743392459',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
        })
        
        # Extract username from ds_user_id cookie and verify
        for cookie in cookie_jar:
            if cookie.name == 'ds_user_id':
                self.loader.context.username = cookie.value
                break
        
        logger.info(f"Loaded cookies with sessionid, attempting to verify...")
    
    def scrape_account(
        self,
        username: str,
        include_stories: bool = False,
        max_posts: Optional[int] = None,
    ) -> ScrapeResult:
        """
        Scrape an Instagram account's posts and optionally stories.
        Downloads media files for analysis.
        
        Note: Posts are scraped without login (public data).
              Stories require login and are scraped separately.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"SCRAPING: @{username}")
        logger.info(f"{'='*60}")
        
        # Ensure download directory exists
        account_dir = self.download_dir / username
        account_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # For posts, use a fresh unauthenticated loader to avoid rate limits
            public_loader = instaloader.Instaloader(
                download_videos=True,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                post_metadata_txt_pattern="",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            
            # Get profile
            profile = instaloader.Profile.from_username(public_loader.context, username)
            
            profile_data = InstagramProfile(
                username=profile.username,
                full_name=profile.full_name or "",
                bio=profile.biography or "",
                followers=profile.followers,
                following=profile.followees,
                post_count=profile.mediacount,
            )
            
            logger.info(f"  Profile: {profile_data.full_name}")
            logger.info(f"  Followers: {profile_data.followers:,}")
            logger.info(f"  Posts: {profile_data.post_count}")
            
            # Scrape posts (public, no login needed)
            posts = self._scrape_posts_public(profile, account_dir, max_posts)
            logger.info(f"  Scraped {len(posts)} posts")
            
            # Scrape stories if requested and logged in
            stories = []
            if include_stories:
                if self._logged_in:
                    # Random delay before stories to avoid rate limits
                    delay = random.uniform(STORY_DELAY_MIN, STORY_DELAY_MAX)
                    logger.info(f"  Waiting {delay:.1f}s before fetching stories...")
                    time.sleep(delay)
                    
                    # Re-fetch profile with authenticated loader for stories
                    try:
                        auth_profile = instaloader.Profile.from_username(self.loader.context, username)
                        stories = self._scrape_stories(auth_profile, account_dir)
                        logger.info(f"  Scraped {len(stories)} stories")
                    except Exception as e:
                        logger.warning(f"  Stories failed: {e}")
                else:
                    logger.warning("  Skipping stories - not logged in")
            
            return ScrapeResult(
                profile=profile_data,
                posts=posts,
                stories=stories,
            )
            
        except instaloader.exceptions.ProfileNotExistsException:
            logger.error(f"Profile @{username} does not exist")
            return ScrapeResult(
                profile=InstagramProfile(username=username, full_name="", bio="", followers=0, following=0, post_count=0),
                error="Profile does not exist"
            )
        except Exception as e:
            logger.error(f"Error scraping @{username}: {e}")
            return ScrapeResult(
                profile=InstagramProfile(username=username, full_name="", bio="", followers=0, following=0, post_count=0),
                error=str(e)
            )
    
    def _scrape_posts_public(
        self,
        profile: instaloader.Profile,
        download_dir: Path,
        max_posts: Optional[int] = None,
    ) -> List[InstagramPost]:
        """Scrape posts and download media"""
        posts = []
        
        logger.info(f"  Scraping posts (max {max_posts or 'all'})...")
        
        for i, post in enumerate(profile.get_posts()):
            if max_posts and i >= max_posts:
                break
                
            try:
                # Determine media type and URL
                is_video = post.is_video
                media_url = post.video_url if is_video else post.url
                
                # Download media
                ext = "mp4" if is_video else "jpg"
                media_path = download_dir / f"{post.shortcode}.{ext}"
                
                if not media_path.exists():
                    self._download_media(media_url, media_path)
                
                instagram_post = InstagramPost(
                    shortcode=post.shortcode,
                    url=f"https://www.instagram.com/p/{post.shortcode}/",
                    caption=post.caption or "",
                    date=post.date_utc.replace(tzinfo=timezone.utc),
                    likes=post.likes,
                    is_video=is_video,
                    is_story=False,
                    media_path=media_path if media_path.exists() else None,
                    video_url=post.video_url if is_video else None,
                )
                
                posts.append(instagram_post)
                
                media_type = "video" if is_video else "image"
                logger.info(f"  [{i+1}] {post.date_utc.strftime('%Y-%m-%d')} - {media_type} - {post.likes} likes")
                
            except Exception as e:
                logger.warning(f"  Failed to process post {post.shortcode}: {e}")
                continue
        
        return posts
    
    def _scrape_stories(
        self,
        profile: instaloader.Profile,
        download_dir: Path,
    ) -> List[InstagramPost]:
        """Scrape stories (requires login)"""
        stories = []
        
        logger.info(f"  Scraping stories...")
        
        try:
            for story in self.loader.get_stories(userids=[profile.userid]):
                for i, item in enumerate(story.get_items()):
                    try:
                        is_video = item.is_video
                        media_url = item.video_url if is_video else item.url
                        
                        # Download media
                        ext = "mp4" if is_video else "jpg"
                        media_path = download_dir / f"story_{item.mediaid}.{ext}"
                        
                        if not media_path.exists():
                            self._download_media(media_url, media_path)
                        
                        story_url = f"https://www.instagram.com/stories/{profile.username}/{item.mediaid}/"
                        
                        # Take screenshot of the story
                        screenshot_path = download_dir / f"story_{item.mediaid}_screenshot.png"
                        screenshot_success = self.take_story_screenshot(
                            story_url=story_url,
                            screenshot_path=screenshot_path,
                            username=profile.username
                        )
                        
                        story_post = InstagramPost(
                            shortcode=str(item.mediaid),
                            url=story_url,
                            caption=item.caption or "",
                            date=item.date_utc.replace(tzinfo=timezone.utc),
                            likes=0,  # Stories don't have public like counts
                            is_video=is_video,
                            is_story=True,
                            media_path=media_path if media_path.exists() else None,
                            video_url=item.video_url if is_video else None,
                            screenshot_path=screenshot_path if screenshot_success else None,
                        )
                        
                        stories.append(story_post)
                        
                        media_type = "video" if is_video else "image"
                        logger.info(f"  [Story {i+1}] {item.date_utc.strftime('%Y-%m-%d %H:%M')} - {media_type}")
                        
                    except Exception as e:
                        logger.warning(f"  Failed to process story item: {e}")
                        continue
                        
        except instaloader.exceptions.LoginRequiredException:
            logger.error("  Login required for stories")
        except Exception as e:
            logger.warning(f"  Error scraping stories: {e}")
        
        return stories
    
    def _download_media(self, url: str, path: Path) -> bool:
        """Download media file from URL"""
        try:
            import urllib.request
            urllib.request.urlretrieve(url, path)
            return True
        except Exception as e:
            logger.warning(f"  Failed to download {url}: {e}")
            return False
    
    def _get_playwright_cookies(self) -> List[dict]:
        """Convert Netscape format cookies.txt to Playwright cookie format"""
        cookies_path = Path(COOKIES_FILE)
        if not cookies_path.exists():
            return []
        
        cookie_jar = http.cookiejar.MozillaCookieJar(str(cookies_path))
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        
        playwright_cookies = []
        for cookie in cookie_jar:
            if 'instagram' in cookie.domain:
                pw_cookie = {
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path or '/',
                }
                # Only add secure/httpOnly if they're set
                if cookie.secure:
                    pw_cookie['secure'] = True
                playwright_cookies.append(pw_cookie)
        
        return playwright_cookies
    
    def _take_screenshot_sync(self, story_url: str, screenshot_path: Path, cookies: List[dict]) -> bool:
        """Internal sync method that runs Playwright - called from a thread pool"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 430, 'height': 932},  # iPhone 14 Pro Max dimensions
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
                )
                
                # Load cookies for authentication
                if cookies:
                    context.add_cookies(cookies)
                
                page = context.new_page()
                
                # Navigate to story URL
                page.goto(story_url, wait_until='networkidle', timeout=30000)
                
                # Wait a bit for initial load
                page.wait_for_timeout(2000)
                
                # Try to click "View Story" button if present
                view_story_selectors = [
                    'button:has-text("View story")',
                    'button:has-text("View Story")',
                    '[role="button"]:has-text("View")',
                    'div[role="button"]:has-text("story")',
                ]
                
                clicked = False
                for selector in view_story_selectors:
                    try:
                        button = page.locator(selector).first
                        if button.is_visible(timeout=2000):
                            button.click()
                            clicked = True
                            page.wait_for_timeout(3000)  # Wait for story to load
                            break
                    except:
                        continue
                
                if not clicked:
                    page.wait_for_timeout(2000)
                
                # Wait for story content to load
                page.wait_for_timeout(1000)
                
                # Take screenshot
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=False)
                
                browser.close()
                
                return screenshot_path.exists()
                
        except Exception as e:
            logger.warning(f"    Screenshot thread failed: {e}")
            return False
    
    def take_story_screenshot(self, story_url: str, screenshot_path: Path, username: str) -> bool:
        """
        Take a screenshot of an Instagram story using Playwright.
        Runs in a separate thread to avoid asyncio conflicts.
        
        Args:
            story_url: Full URL to the story
            screenshot_path: Path to save the screenshot
            username: Instagram username for logging
            
        Returns:
            True if screenshot was taken successfully, False otherwise
        """
        try:
            logger.info(f"    Taking screenshot of story...")
            
            cookies = self._get_playwright_cookies()
            if cookies:
                logger.info(f"    Loaded {len(cookies)} cookies for auth")
            
            # Run Playwright in a separate thread to avoid asyncio conflicts
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._take_screenshot_sync,
                    story_url,
                    screenshot_path,
                    cookies
                )
                success = future.result(timeout=60)
            
            if success:
                logger.info(f"    ↳ Screenshot saved: {screenshot_path.name}")
                return True
            else:
                logger.warning(f"    Screenshot file not created")
                return False
                
        except Exception as e:
            logger.warning(f"    Screenshot failed: {e}")
            return False
    
    def cleanup(self, username: str):
        """Remove downloaded media for an account"""
        account_dir = self.download_dir / username
        if account_dir.exists():
            shutil.rmtree(account_dir)
            logger.info(f"Cleaned up media for @{username}")

