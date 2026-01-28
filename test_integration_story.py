#!/usr/bin/env python3
"""
Integration test: Full story scrape + analysis flow using Playwright/Firefox.
Tests with defendourjuries account.
"""

import sys
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from scraper import InstagramScraper
from analyzer import InstagramAnalyzer
from config import GEMINI_API_KEY

TEST_USERNAME = "defendourjuries"

def main():
    print(f"\n{'='*60}")
    print(f"INTEGRATION TEST: Story Scraping + Analysis")
    print(f"{'='*60}")
    print(f"Account: @{TEST_USERNAME}")
    
    # Initialize components
    print(f"\n1. Initializing scraper...")
    scraper = InstagramScraper()
    
    # Login for story access
    print(f"\n2. Loading cookies...")
    if not scraper.login():
        print("WARNING: Login failed, stories may not work")
    
    # Scrape account with stories
    print(f"\n3. Scraping account (with stories)...")
    result = scraper.scrape_account(
        username=TEST_USERNAME,
        include_stories=True,
        max_posts=5,  # Limit posts to keep test quick
    )
    
    if result.error:
        print(f"ERROR: {result.error}")
        return 1
    
    print(f"\n4. Scrape Results:")
    print(f"   Profile: {result.profile.full_name} (@{result.profile.username})")
    print(f"   Posts scraped: {len(result.posts)}")
    print(f"   Stories scraped: {len(result.stories)}")
    
    if not result.stories:
        print("   No stories found - account may have no active stories")
        return 0
    
    # Show story details
    print(f"\n5. Story Details:")
    for i, story in enumerate(result.stories):
        print(f"\n   Story {i+1}:")
        print(f"     ID: {story.shortcode}")
        print(f"     URL: {story.url}")
        print(f"     Type: {'video' if story.is_video else 'image'}")
        print(f"     Media: {story.media_path.name if story.media_path else 'None'}")
        print(f"     Screenshot: {story.screenshot_path.name if story.screenshot_path else 'None'}")
        if story.video_url:
            print(f"     Video URL: {story.video_url[:60]}...")
    
    # Test analysis if API key available
    if GEMINI_API_KEY:
        print(f"\n6. Testing AI Analysis...")
        analyzer = InstagramAnalyzer()
        
        # Analyze first story
        test_story = result.stories[0]
        print(f"   Analyzing story {test_story.shortcode}...")
        
        try:
            analysis = analyzer.analyze_scrape_result(result)
            print(f"   Analysis complete!")
            print(f"   Flagged items: {len(analysis.flagged_items)}")
            
            for item in analysis.flagged_items[:3]:
                print(f"\n   Flagged: {item.get('shortcode')}")
                print(f"     Reason: {item.get('reason', 'N/A')[:100]}...")
                if item.get('video_transcript'):
                    print(f"     Transcript: {item.get('video_transcript')[:100]}...")
        except Exception as e:
            print(f"   Analysis error: {e}")
    else:
        print(f"\n6. Skipping analysis (no GEMINI_API_KEY)")
    
    # Cleanup
    print(f"\n7. Cleaning up...")
    scraper.cleanup(TEST_USERNAME)
    
    print(f"\n{'='*60}")
    print(f"TEST COMPLETE")
    print(f"{'='*60}\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
