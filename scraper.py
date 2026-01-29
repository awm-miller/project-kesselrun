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
from zoneinfo import ZoneInfo

import instaloader
import asyncio
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

from config import (
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    TEMP_DIR,
    COOKIES_FILE,
    STORY_DELAY_MIN,
    STORY_DELAY_MAX,
    STORY_ITEM_DELAY,
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
        """Scrape stories - uses Playwright/Firefox (bypasses Instagram API blocks)"""
        stories = []
        username = profile.username
        
        logger.info(f"  Scraping stories via Playwright/Firefox...")
        
        try:
            # Run Playwright in a thread to avoid asyncio loop conflicts
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._scrape_stories_playwright, username, download_dir)
                stories = future.result(timeout=300)  # 5 minute timeout
        except Exception as e:
            logger.warning(f"  Playwright story scraping failed: {e}")
            # Fallback to instaloader API (may fail but worth trying)
            logger.info(f"  Trying fallback to instaloader API...")
            stories = self._scrape_stories_instaloader(profile, download_dir)
        
        return stories
    
    def _scrape_stories_playwright(
        self,
        username: str,
        download_dir: Path,
    ) -> List[InstagramPost]:
        """Scrape stories using Playwright/Firefox browser automation."""
        import re
        
        stories = []
        cookies = self._get_playwright_cookies()
        
        if not cookies:
            logger.warning("  No cookies available for Playwright")
            return stories
        
        logger.info(f"  Loaded {len(cookies)} cookies for Firefox")
        
        with sync_playwright() as p:
            # Use Firefox - it has better video playback in headless mode
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                viewport={'width': 1280, 'height': 900},
            )
            context.add_cookies(cookies)
            page = context.new_page()
            
            # Intercept video CDN URLs - use route to capture ALL requests
            captured_video_urls = []
            def handle_route(route):
                url = route.request.url
                # Instagram video CDN URLs contain these patterns
                if ('.mp4' in url or 'video' in url.lower()) and ('cdninstagram.com' in url or 'fbcdn.net' in url):
                    captured_video_urls.append(url)
                route.continue_()
            
            # Intercept all requests to CDN
            page.route("**/*cdninstagram.com*", handle_route)
            page.route("**/*fbcdn.net*", handle_route)
            
            # Navigate to stories
            story_url = f"https://www.instagram.com/stories/{username}/"
            logger.info(f"  Navigating to: {story_url}")
            page.goto(story_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # Click "View story" if present
            view_btn = page.get_by_text("View story", exact=False)
            if view_btn.count() > 0:
                logger.info(f"  Clicking 'View story'...")
                view_btn.first.click()
                time.sleep(3)
            
            # Wait for story to fully load after clicking view
            time.sleep(3)
            
            # Check if we have stories
            current_url = page.url
            if "/stories/" not in current_url or username not in current_url:
                logger.info(f"  No stories available for @{username}")
                browser.close()
                return stories
            
            # Scrape each story
            story_count = 0
            max_stories = 30  # Safety limit
            seen_ids = set()
            
            while story_count < max_stories:
                current_url = page.url
                
                # Check if we've left stories section
                if "/stories/" not in current_url:
                    logger.info(f"  Left stories section")
                    break
                
                # Extract story ID from URL (may not be present for first story)
                match = re.search(r'/stories/[^/]+/(\d+)', current_url)
                story_id = match.group(1) if match else None
                
                # If no ID in URL, try to get it from page data or generate temp ID
                if not story_id:
                    # Try clicking to advance to get a proper URL with ID
                    if story_count == 0:
                        # First story - advance once to get proper URL
                        logger.info(f"  First story - advancing to get story ID...")
                        page.mouse.click(page.viewport_size['width'] - 100, page.viewport_size['height'] // 2)
                        time.sleep(3)
                        current_url = page.url
                        match = re.search(r'/stories/[^/]+/(\d+)', current_url)
                        story_id = match.group(1) if match else f"temp_{story_count}"
                    else:
                        story_id = f"temp_{story_count}"
                
                # Check if we've looped back
                if story_id in seen_ids:
                    logger.info(f"  Reached end (looped back to {story_id})")
                    break
                seen_ids.add(story_id)
                
                story_count += 1
                
                # Delay between stories (except first)
                if story_count > 1:
                    logger.info(f"    Waiting {STORY_ITEM_DELAY}s before next story...")
                    time.sleep(STORY_ITEM_DELAY)
                
                # Check if it's a video
                is_video = False
                video_url = None
                video_elem = page.query_selector('video')
                if video_elem:
                    is_video = True
                    # Remember how many URLs we had before this video
                    urls_before = len(captured_video_urls)
                    
                    # Wait for video to load and start playing (triggers network request)
                    time.sleep(1)
                    try:
                        # Force video to play and load
                        page.evaluate("""
                            const video = document.querySelector('video');
                            if (video) {
                                video.currentTime = 0;
                                video.play();
                            }
                        """)
                        time.sleep(3)  # Give time for video to load from CDN
                    except:
                        pass
                    
                    # Get the actual CDN URL from captured network requests (new ones since this video)
                    new_urls = captured_video_urls[urls_before:]
                    if new_urls:
                        video_url = new_urls[-1]  # Most recent video URL for this story
                        logger.info(f"    ↳ Captured video CDN URL")
                    else:
                        # Fallback - try to get src directly (might be blob)
                        try:
                            video_url = page.evaluate("document.querySelector('video')?.src")
                            if video_url and not video_url.startswith('blob:'):
                                logger.info(f"    ↳ Got video src directly")
                        except:
                            pass
                
                # Try to get image URL if not video
                image_url = None
                if not is_video:
                    try:
                        img_elem = page.query_selector('img[srcset], img[src*="instagram"]')
                        if img_elem:
                            srcset = img_elem.get_attribute('srcset')
                            if srcset:
                                # Get highest resolution from srcset
                                parts = srcset.split(',')
                                image_url = parts[-1].strip().split()[0]
                            else:
                                image_url = img_elem.get_attribute('src')
                    except:
                        pass
                
                media_type = "video" if is_video else "image"
                logger.info(f"  [Story {story_count}] ID: {story_id} - {media_type}")
                
                # Take screenshot
                screenshot_path = download_dir / f"story_{story_id}_screenshot.png"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path))
                self._add_timestamp_to_screenshot(screenshot_path)
                logger.info(f"    ↳ Screenshot: {screenshot_path.name}")
                
                # Download media
                media_url = video_url if is_video else image_url
                media_path = None
                if media_url:
                    ext = "mp4" if is_video else "jpg"
                    media_path = download_dir / f"story_{story_id}.{ext}"
                    if self._download_media(media_url, media_path):
                        logger.info(f"    ↳ Media downloaded: {media_path.name}")
                    else:
                        media_path = None
                
                # Create story post object
                story_post = InstagramPost(
                    shortcode=story_id,
                    url=f"https://www.instagram.com/stories/{username}/{story_id}/",
                    caption="",  # Stories rarely have captions accessible via browser
                    date=datetime.now(timezone.utc),
                    likes=0,
                    is_video=is_video,
                    is_story=True,
                    media_path=media_path,
                    video_url=video_url,
                    screenshot_path=screenshot_path if screenshot_path.exists() else None,
                )
                stories.append(story_post)
                
                # Navigate to next story (click right side)
                try:
                    page.mouse.click(page.viewport_size['width'] - 100, page.viewport_size['height'] // 2)
                    time.sleep(2)
                    
                    # If URL didn't change, try arrow key
                    if page.url == current_url:
                        page.keyboard.press("ArrowRight")
                        time.sleep(2)
                        if page.url == current_url:
                            logger.info(f"  No more stories")
                            break
                except Exception as e:
                    logger.warning(f"  Navigation error: {e}")
                    break
            
            browser.close()
        
        logger.info(f"  Scraped {len(stories)} stories via Playwright")
        return stories
    
    def _scrape_stories_instaloader(
        self,
        profile: instaloader.Profile,
        download_dir: Path,
    ) -> List[InstagramPost]:
        """Fallback: Scrape stories using instaloader API (often blocked)"""
        stories = []
        
        try:
            for story in self.loader.get_stories(userids=[profile.userid]):
                for i, item in enumerate(story.get_items()):
                    try:
                        if i > 0:
                            logger.info(f"    Waiting {STORY_ITEM_DELAY}s before next story item...")
                            time.sleep(STORY_ITEM_DELAY)
                        
                        is_video = item.is_video
                        media_url = item.video_url if is_video else item.url
                        
                        ext = "mp4" if is_video else "jpg"
                        media_path = download_dir / f"story_{item.mediaid}.{ext}"
                        
                        if not media_path.exists():
                            self._download_media(media_url, media_path)
                        
                        story_url = f"https://www.instagram.com/stories/{profile.username}/{item.mediaid}/"
                        
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
                            likes=0,
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
            logger.error("  Login required for stories (API blocked)")
        except Exception as e:
            logger.warning(f"  Instaloader API error: {e}")
        
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
    
    def _add_timestamp_to_screenshot(self, screenshot_path: Path) -> bool:
        """Add a British time timestamp to the bottom right of a screenshot"""
        try:
            # Open the screenshot
            img = Image.open(screenshot_path)
            draw = ImageDraw.Draw(img)
            
            # Get current time in British timezone
            uk_tz = ZoneInfo("Europe/London")
            uk_time = datetime.now(uk_tz)
            timestamp_text = uk_time.strftime("%d/%m/%Y %H:%M:%S GMT")
            
            # Try to use a decent font, fall back to default
            font_size = 24
            try:
                # Try common system fonts
                for font_name in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
                    try:
                        font = ImageFont.truetype(font_name, font_size)
                        break
                    except:
                        continue
                else:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            # Calculate text position (bottom right with padding)
            bbox = draw.textbbox((0, 0), timestamp_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            padding = 15
            x = img.width - text_width - padding
            y = img.height - text_height - padding
            
            # Draw background rectangle for readability
            bg_padding = 5
            draw.rectangle(
                [x - bg_padding, y - bg_padding, x + text_width + bg_padding, y + text_height + bg_padding],
                fill=(0, 0, 0, 180)  # Semi-transparent black
            )
            
            # Draw timestamp in bright green
            bright_green = (0, 255, 0)  # RGB for bright green
            draw.text((x, y), timestamp_text, font=font, fill=bright_green)
            
            # Save the image
            img.save(screenshot_path)
            return True
            
        except Exception as e:
            logger.warning(f"    Failed to add timestamp to screenshot: {e}")
            return False
    
    def _take_screenshot_sync(self, story_url: str, screenshot_path: Path, cookies: List[dict]) -> bool:
        """Internal sync method that runs Playwright - called from a thread pool"""
        try:
            with sync_playwright() as p:
                # Use Firefox for better video playback support in headless mode
                browser = p.firefox.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 430, 'height': 932},  # iPhone 14 Pro Max dimensions
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
                )
                
                # Load cookies for authentication
                if cookies:
                    context.add_cookies(cookies)
                
                page = context.new_page()
                
                # Navigate to story URL
                page.goto(story_url, wait_until='domcontentloaded', timeout=30000)
                
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
                
                # Add timestamp overlay to the screenshot
                if screenshot_path.exists():
                    self._add_timestamp_to_screenshot(screenshot_path)
                
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

