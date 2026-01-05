#!/usr/bin/env python3
"""
Instagram Monitor - Main Entry Point

Monitors multiple Instagram accounts, analyzing posts, videos, and stories.
Designed to run as a cron job on a VPS.

Usage:
    python monitor.py [--accounts accounts.json] [--max-posts 100]
"""
import os
import sys
import json
import logging
import asyncio
import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import time

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

from config import (
    ACCOUNT_DELAY_MIN,
    ACCOUNT_DELAY_MAX,
    ACCOUNTS_FILE,
    RESULTS_DIR,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    INSTAGRAM_USERNAME,
    COOKIES_FILE,
)
from scraper import InstagramScraper
from analyzer import InstagramAnalyzer, AnalysisResult

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
)
logger = logging.getLogger("monitor")


def load_accounts(filepath: str) -> List[Dict[str, Any]]:
    """Load accounts from JSON file"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data.get("accounts", [])


def save_result(filepath: str, result: AnalysisResult):
    """Save analysis result to JSON file"""
    output = {
        "username": result.username,
        "analyzed_at": datetime.utcnow().isoformat(),
        "profile": result.profile,
        "summary": result.summary,
        "stats": {
            "total_posts": result.total_posts,
            "total_stories": result.total_stories,
            "flagged_count": result.flagged_count,
        },
        "posts": result.posts,
        "error": result.error,
    }
    
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to {filepath}")


async def process_account(
    scraper: InstagramScraper,
    analyzer: InstagramAnalyzer,
    account: Dict[str, Any],
    max_posts: int = None,
) -> AnalysisResult:
    """Process a single Instagram account"""
    username = account["username"]
    include_stories = account.get("include_stories", False)
    
    # Scrape account
    scrape_result = scraper.scrape_account(
        username=username,
        include_stories=include_stories,
        max_posts=max_posts,
    )
    
    # Analyze content
    analysis_result = analyzer.analyze_scrape_result(scrape_result)
    
    # Cleanup downloaded media
    scraper.cleanup(username)
    
    return analysis_result


async def main(accounts_file: str, max_posts: int = None):
    """Main monitoring loop"""
    logger.info("=" * 60)
    logger.info("INSTAGRAM MONITOR STARTING")
    logger.info("=" * 60)
    
    # Load accounts
    accounts = load_accounts(accounts_file)
    logger.info(f"Loaded {len(accounts)} accounts to monitor")
    
    if not accounts:
        logger.error("No accounts configured")
        return
    
    # Initialize components
    scraper = InstagramScraper()
    analyzer = InstagramAnalyzer()
    
    # Check if any account needs stories
    needs_stories = any(a.get("include_stories", False) for a in accounts)
    
    # Login if stories needed (will try cookies first, then username/password)
    if needs_stories:
        cookies_exist = Path(COOKIES_FILE).exists()
        if cookies_exist or INSTAGRAM_USERNAME:
            logger.info("Attempting Instagram login for story access...")
            scraper.login()
        else:
            logger.warning("Stories requested but no authentication configured")
    
    # Process each account
    for i, account in enumerate(accounts):
        username = account["username"]
        logger.info(f"\n[{i+1}/{len(accounts)}] Processing @{username}...")
        
        try:
            result = await process_account(
                scraper=scraper,
                analyzer=analyzer,
                account=account,
                max_posts=max_posts,
            )
            
            # Save results
            output_path = Path(RESULTS_DIR) / f"{username}.json"
            save_result(str(output_path), result)
            
            # Print summary
            logger.info(f"\n  Summary for @{username}:")
            logger.info(f"    Posts analyzed: {result.total_posts}")
            logger.info(f"    Stories analyzed: {result.total_stories}")
            logger.info(f"    Flagged items: {result.flagged_count}")
            if result.error:
                logger.error(f"    Error: {result.error}")
            
        except Exception as e:
            logger.error(f"Failed to process @{username}: {e}")
        
        # Wait between accounts (random delay for anti-bot detection)
        if i < len(accounts) - 1:
            delay = random.uniform(ACCOUNT_DELAY_MIN, ACCOUNT_DELAY_MAX)
            logger.info(f"\nWaiting {delay:.0f}s before next account...")
            await asyncio.sleep(delay)
    
    logger.info("\n" + "=" * 60)
    logger.info("INSTAGRAM MONITOR COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Monitor")
    parser.add_argument(
        "--accounts",
        default=ACCOUNTS_FILE,
        help=f"Path to accounts JSON file (default: {ACCOUNTS_FILE})"
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help="Maximum posts to scrape per account (default: all)"
    )
    
    args = parser.parse_args()
    
    # Change to script directory for relative paths
    os.chdir(Path(__file__).parent)
    
    asyncio.run(main(args.accounts, args.max_posts))

