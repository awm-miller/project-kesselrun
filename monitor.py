#!/usr/bin/env python3
"""
Instagram Monitor - Main Entry Point (Production Version)

Monitors multiple Instagram accounts with:
- State tracking (only analyze new content)
- Google Drive upload (JSON + media)
- Report generation (HTML + PDF)
- Email notifications

Designed to run as a daily cron job on a VPS.

Usage:
    python monitor.py [--accounts accounts.json] [--max-posts 100] [--test]
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
    STATE_FILE,
    SUBSCRIBERS_FILE,
    GOOGLE_SERVICE_ACCOUNT_PATH,
    GOOGLE_DRIVE_ROOT_FOLDER_ID,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    TEMPLATES_DIR,
    TEMP_DIR,
)
from scraper import InstagramScraper
from analyzer import InstagramAnalyzer, AnalysisResult
from state_tracker import StateTracker
from gdrive_uploader import GoogleDriveUploader
from reporter import ReportGenerator
from emailer import EmailSender, load_subscribers

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


def save_result_local(filepath: str, result: AnalysisResult):
    """Save analysis result to local JSON file (optional, for backward compatibility)"""
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
    
    logger.info(f"Local results saved to {filepath}")


async def process_account(
    scraper: InstagramScraper,
    analyzer: InstagramAnalyzer,
    state_tracker: StateTracker,
    gdrive_uploader: GoogleDriveUploader,
    report_generator: ReportGenerator,
    account: Dict[str, Any],
    max_posts: int = None,
    test_mode: bool = False,
) -> Dict[str, Any]:
    """
    Process a single Instagram account with full pipeline
    
    Returns dict with:
        - analysis_result: The AnalysisResult object
        - report_paths: Dict with html/pdf paths (not deleted, for email attachment)
        - folder_url: Google Drive folder URL
        - flagged_items: List of flagged content for summary email
    """
    username = account["username"]
    include_stories = account.get("include_stories", False)
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    result_data = {
        'username': username,
        'analysis_result': None,
        'report_paths': {'html': None, 'pdf': None},
        'folder_url': None,
        'flagged_items': [],
        'date_str': date_str,
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"PROCESSING: @{username}")
    logger.info(f"{'='*60}")
    
    # Step 1: Scrape account (all content)
    logger.info("Step 1: Scraping content...")
    scrape_result = scraper.scrape_account(
        username=username,
        include_stories=include_stories,
        max_posts=max_posts,
    )
    
    if scrape_result.error:
        logger.error(f"Scraping failed: {scrape_result.error}")
        result_data['analysis_result'] = AnalysisResult(
            username=username,
            profile={"username": username},
            summary="",
            error=scrape_result.error
        )
        return result_data
    
    # Step 2: Filter to NEW content only
    logger.info("Step 2: Filtering new content...")
    new_posts = state_tracker.filter_new_posts(username, scrape_result.posts)
    new_stories = state_tracker.filter_new_stories(username, scrape_result.stories)
    
    if not new_posts and not new_stories:
        logger.info(f"No new content for @{username} - skipping analysis")
        scraper.cleanup(username)
        result_data['analysis_result'] = AnalysisResult(
            username=username,
            profile=analyzer._profile_to_dict(scrape_result.profile),
            summary=f"No new content since last run. Account has {scrape_result.profile.post_count} total posts.",
            posts=[],
            total_posts=0,
            total_stories=0,
            flagged_count=0
        )
        return result_data
    
    logger.info(f"Found {len(new_posts)} new posts and {len(new_stories)} new stories")
    
    # Step 3: Analyze NEW content
    logger.info("Step 3: Analyzing new content...")
    
    # Create a modified scrape result with only new content
    from scraper import ScrapeResult
    new_content_result = ScrapeResult(
        profile=scrape_result.profile,
        posts=new_posts,
        stories=new_stories
    )
    
    # Media files are uploaded to Google Drive during analysis (if gdrive_uploader is available)
    analysis_result = analyzer.analyze_scrape_result(new_content_result, date_str=date_str)
    
    # Step 4: Media upload happens during analysis - just log status
    if not test_mode and gdrive_uploader:
        uploaded_count = sum(1 for p in analysis_result.posts if p.get('gdrive_file_id'))
        logger.info(f"Step 4: {uploaded_count} media files uploaded to Google Drive during analysis")
        # Get folder URL for summary email
        result_data['folder_url'] = gdrive_uploader.get_folder_url(username, date_str)
    elif test_mode:
        logger.info("Step 4: Skipping Google Drive upload (test mode)")
    
    # Step 5: Generate reports (HTML + PDF)
    logger.info("Step 5: Generating reports...")
    try:
        report_paths = report_generator.generate_report(
            username=username,
            profile=analysis_result.profile,
            summary=analysis_result.summary,
            posts=analysis_result.posts,
            stories=[],  # Stories are already in posts list
            stats={
                'total_posts': analysis_result.total_posts,
                'total_stories': analysis_result.total_stories,
                'flagged_count': analysis_result.flagged_count
            },
            date_str=date_str
        )
        result_data['report_paths'] = report_paths
        
        # Upload PDF report to Google Drive (skip HTML)
        if not test_mode and gdrive_uploader:
            try:
                pdf_path = report_paths.get('pdf')
                if pdf_path:
                    gdrive_uploader.upload_report(
                        local_path=Path(pdf_path),
                        username=username,
                        date_str=date_str
                    )
            except Exception as e:
                logger.error(f"Failed to upload PDF to Google Drive: {e}")
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        report_paths = {'html': None, 'pdf': None}
    
    # Step 6: Build flagged items list for summary email
    logger.info("Step 6: Collecting flagged content for summary...")
    for post in analysis_result.posts:
        if post.get('flagged'):
            gdrive_url = None
            if post.get('gdrive_file_id') and gdrive_uploader:
                gdrive_url = gdrive_uploader.get_file_url(post['gdrive_file_id'])
            
            result_data['flagged_items'].append({
                'type': 'story' if post.get('is_story') else 'post',
                'url': post.get('url', ''),
                'reason': post.get('flag_reason', ''),
                'gdrive_url': gdrive_url,
                'media_description': post.get('media_description', ''),
                'date': post.get('date', ''),
            })
    
    # Step 7: Update state tracker
    logger.info("Step 7: Updating state...")
    post_shortcodes = [p.shortcode for p in new_posts]
    story_ids = [s.shortcode for s in new_stories]
    state_tracker.mark_analyzed(
        username=username,
        post_shortcodes=post_shortcodes,
        story_ids=story_ids
    )
    
    # Step 8: Cleanup temp downloads (but keep report files for summary email)
    logger.info("Step 8: Cleaning up temp downloads...")
    scraper.cleanup(username)
    
    logger.info(f"Processing complete for @{username}")
    
    result_data['analysis_result'] = analysis_result
    return result_data


async def main(accounts_file: str, max_posts: int = None, test_mode: bool = False):
    """Main monitoring loop"""
    logger.info("=" * 60)
    logger.info("INSTAGRAM MONITOR STARTING")
    if test_mode:
        logger.info("TEST MODE - No uploads or emails")
    logger.info("=" * 60)
    
    # Load accounts
    accounts = load_accounts(accounts_file)
    logger.info(f"Loaded {len(accounts)} accounts to monitor")
    
    if not accounts:
        logger.error("No accounts configured")
        return
    
    # Initialize components
    logger.info("\nInitializing components...")
    scraper = InstagramScraper()
    state_tracker = StateTracker(STATE_FILE)
    
    # Initialize Google Drive uploader
    gdrive_uploader = None
    if not test_mode:
        try:
            gdrive_uploader = GoogleDriveUploader(
                service_account_path=GOOGLE_SERVICE_ACCOUNT_PATH,
                root_folder_id=GOOGLE_DRIVE_ROOT_FOLDER_ID
            )
        except Exception as e:
            logger.error(f"Google Drive initialization failed: {e}")
            logger.warning("Continuing without Google Drive support")
    
    # Initialize analyzer with Google Drive uploader (uploads media during analysis)
    analyzer = InstagramAnalyzer(gdrive_uploader=gdrive_uploader)
    
    # Initialize report generator
    report_generator = ReportGenerator(templates_dir=TEMPLATES_DIR)
    
    # Initialize email sender
    email_sender = None
    subscribers = []
    if not test_mode and SMTP_USERNAME and SMTP_PASSWORD:
        try:
            email_sender = EmailSender(
                smtp_server=SMTP_SERVER,
                smtp_port=SMTP_PORT,
                username=SMTP_USERNAME,
                password=SMTP_PASSWORD,
                from_email=SMTP_FROM_EMAIL,
                from_name=SMTP_FROM_NAME
            )
            subscribers = load_subscribers(SUBSCRIBERS_FILE)
        except Exception as e:
            logger.error(f"Email sender initialization failed: {e}")
            logger.warning("Continuing without email support")
    
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
    
    # Process each account and collect results
    all_results = []
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    for i, account in enumerate(accounts):
        username = account["username"]
        logger.info(f"\n[{i+1}/{len(accounts)}] Processing @{username}...")
        
        try:
            result_data = await process_account(
                scraper=scraper,
                analyzer=analyzer,
                state_tracker=state_tracker,
                gdrive_uploader=gdrive_uploader,
                report_generator=report_generator,
                account=account,
                max_posts=max_posts,
                test_mode=test_mode,
            )
            all_results.append(result_data)
            
            # Print summary
            analysis = result_data.get('analysis_result')
            if analysis:
                logger.info(f"\n  Summary for @{username}:")
                logger.info(f"    New posts analyzed: {analysis.total_posts}")
                logger.info(f"    New stories analyzed: {analysis.total_stories}")
                logger.info(f"    Flagged items: {analysis.flagged_count}")
                if analysis.error:
                    logger.error(f"    Error: {analysis.error}")
            
            # Show state stats
            stats = state_tracker.get_stats(username)
            logger.info(f"    Total tracked: {stats['total_posts_analyzed']} posts, "
                       f"{stats['total_stories_analyzed']} stories")
            
        except Exception as e:
            logger.error(f"Failed to process @{username}: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait between accounts (random delay for anti-bot detection)
        if i < len(accounts) - 1:
            delay = random.uniform(ACCOUNT_DELAY_MIN, ACCOUNT_DELAY_MAX)
            logger.info(f"\nWaiting {delay:.0f}s before next account...")
            await asyncio.sleep(delay)
    
    # Send aggregated summary email
    if not test_mode and email_sender and subscribers and all_results:
        logger.info("\n" + "=" * 60)
        logger.info("SENDING DAILY SUMMARY EMAIL")
        logger.info("=" * 60)
        
        # Build account results for summary
        account_results = []
        pdf_attachments = []
        
        for result_data in all_results:
            analysis = result_data.get('analysis_result')
            if not analysis:
                continue
            
            account_results.append({
                'username': result_data['username'],
                'folder_url': result_data.get('folder_url', ''),
                'total_posts': analysis.total_posts,
                'total_stories': analysis.total_stories,
                'flagged_count': analysis.flagged_count,
                'flagged_items': result_data.get('flagged_items', []),
            })
            
            # Collect PDF paths
            pdf_path = result_data.get('report_paths', {}).get('pdf')
            if pdf_path and Path(pdf_path).exists():
                pdf_attachments.append(Path(pdf_path))
        
        try:
            email_sent = email_sender.send_daily_summary(
                recipients=subscribers,
                date_str=date_str,
                account_results=account_results,
                pdf_attachments=pdf_attachments
            )
            if email_sent:
                logger.info(f"Daily summary sent to {len(subscribers)} subscriber(s) with {len(pdf_attachments)} PDF attachments")
            else:
                logger.warning("Daily summary email sending failed")
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")
    elif test_mode:
        logger.info("\nSkipping summary email (test mode)")
    
    # Cleanup: Delete temporary report files
    logger.info("\nCleaning up temporary report files...")
    for result_data in all_results:
        for report_path in result_data.get('report_paths', {}).values():
            if report_path and Path(report_path).exists():
                try:
                    Path(report_path).unlink()
                except:
                    pass
    
    logger.info("\n" + "=" * 60)
    logger.info("INSTAGRAM MONITOR COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Monitor (Production)")
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
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: skip Google Drive uploads and emails"
    )
    
    args = parser.parse_args()
    
    # Change to script directory for relative paths
    os.chdir(Path(__file__).parent)
    
    asyncio.run(main(args.accounts, args.max_posts, args.test))
