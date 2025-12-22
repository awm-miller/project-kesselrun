"""
Gemini Analyzer for Instagram Content (Images + Videos)
"""
import os
import logging
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import google.generativeai as genai
from PIL import Image

from config import GEMINI_API_KEY, GEMINI_MODEL
from scraper import InstagramPost, InstagramProfile, ScrapeResult

logger = logging.getLogger("analyzer")


@dataclass
class AnalysisResult:
    """Result of content analysis"""
    username: str
    profile: Dict[str, Any]
    summary: str
    posts: List[Dict[str, Any]] = field(default_factory=list)
    flagged_count: int = 0
    total_posts: int = 0
    total_stories: int = 0
    error: Optional[str] = None


class InstagramAnalyzer:
    """Analyzes Instagram content using Gemini 2.0 Flash"""
    
    # Prompt for image analysis
    IMAGE_PROMPT = """Describe this Instagram image in 2-3 sentences.
Focus on: people, symbols, flags, text overlays, gestures, locations.
Specifically highlight any imagery which is antisemitic, anti-Zionist, or in support of proscribed terrorist organisations (Hamas, Hezbollah, etc).
Be factual and objective."""

    # Prompt for video analysis
    VIDEO_PROMPT = """Analyze this Instagram video comprehensively:

1. TRANSCRIBE all speech/audio - include the full transcript
2. DESCRIBE key visual content: people, symbols, flags, text overlays, locations, gestures
3. FLAG any content that is antisemitic, anti-Zionist, or in support of proscribed terrorist organisations (Hamas, Hezbollah, etc)

Be factual and objective. Provide a complete analysis.Include the FULL TRANSCRIPT and then your analysis."""

    # Prompt for final analysis
    ANALYSIS_PROMPT = """You are a forensic analyst examining the Instagram activity of @{username}.

MATERIAL VOLUME: {total_posts} total posts are provided below for analysis.
Each post has an INDEX number. Use these indices to identify posts.

TASK 1: Write a ONE PARAGRAPH clinical summary (4-6 sentences max).
Include: volume analyzed, main topics, and any notable patterns.
Be concise and factual.

TASK 2: Identify the MOST CONTROVERSIAL posts by their INDEX number.
Flag only posts that are CLEARLY problematic - not just political opinions. Look for:
- Genuinely inflammatory, offensive, or hateful statements
- Content that could cause serious public backlash
- Statements that are objectively concerning (threats, slurs, etc.)
- Antisemitic, anti-Zionist, or pro-terrorist content
- Support for proscribed terrorist organisations (Hamas, Hezbollah, etc)

Do NOT flag normal political opinions or criticism.

POSTS DATA:
{posts_data}

RESPOND WITH VALID JSON ONLY (no markdown, no extra text):
{{
  "summary": "Your clinical summary here - 4-6 sentences, factual and objective.",
  "flagged": [
    {{"index": 0, "reason": "Short reason why controversial"}},
    {{"index": 5, "reason": "Short reason why controversial"}}
  ]
}}"""

    def __init__(self, gdrive_uploader=None):
        """
        Initialize the analyzer
        
        Args:
            gdrive_uploader: Optional GoogleDriveUploader instance for uploading media during analysis
        """
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=16384,
            )
        )
        self.vision_model = genai.GenerativeModel(GEMINI_MODEL)
        self.gdrive_uploader = gdrive_uploader
        logger.info(f"Analyzer initialized with {GEMINI_MODEL}")
    
    def analyze_scrape_result(self, result: ScrapeResult, date_str: str = None) -> AnalysisResult:
        """
        Analyze a complete scrape result
        
        Args:
            result: ScrapeResult from scraper
            date_str: Date string (YYYY-MM-DD) for Google Drive folder structure
        """
        from datetime import datetime
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            
        if result.error:
            return AnalysisResult(
                username=result.profile.username,
                profile=self._profile_to_dict(result.profile),
                summary="",
                error=result.error,
            )
        
        logger.info(f"\n{'='*60}")
        logger.info(f"ANALYZING: @{result.profile.username}")
        logger.info(f"{'='*60}")
        
        # Combine posts and stories
        all_content = result.posts + result.stories
        
        if not all_content:
            return AnalysisResult(
                username=result.profile.username,
                profile=self._profile_to_dict(result.profile),
                summary="No posts or stories found to analyze.",
                total_posts=0,
                total_stories=0,
            )
        
        # Step 1: Analyze each piece of media AND upload to Google Drive
        upload_msg = " + uploading to Google Drive" if self.gdrive_uploader else ""
        logger.info(f"  Step 1: Analyzing {len(all_content)} media items{upload_msg}...")
        analyzed_posts = []
        
        for i, post in enumerate(all_content):
            media_type = 'video' if post.is_video else 'image'
            content_type = 'STORIES' if post.is_story else 'POSTS'
            logger.info(f"  [{i+1}/{len(all_content)}] Analyzing {media_type}...")
            
            description = ""
            gdrive_file_id = None
            
            if post.media_path and post.media_path.exists():
                # Analyze with Gemini
                if post.is_video:
                    description = self._analyze_video(post.media_path)
                else:
                    description = self._analyze_image(post.media_path)
                
                # Upload to Google Drive simultaneously
                if self.gdrive_uploader:
                    try:
                        gdrive_file_id = self.gdrive_uploader.upload_file(
                            local_path=post.media_path,
                            username=result.profile.username,
                            content_type=content_type,
                            date_str=date_str
                        )
                        if gdrive_file_id:
                            logger.info(f"    ↳ Uploaded to Google Drive: {post.media_path.name}")
                    except Exception as e:
                        logger.warning(f"    ↳ Failed to upload to Google Drive: {e}")
            
            analyzed_posts.append({
                "index": i,
                "shortcode": post.shortcode,
                "url": post.url,
                "date": post.date.isoformat(),
                "caption": post.caption[:500] if post.caption else "",
                "is_video": post.is_video,
                "is_story": post.is_story,
                "likes": post.likes,
                "media_description": description,
                "media_path": str(post.media_path) if post.media_path else None,
                "gdrive_file_id": gdrive_file_id,
            })
        
        # Step 2: Run comprehensive analysis
        logger.info(f"  Step 2: Running comprehensive analysis...")
        summary, flagged = self._run_analysis(
            result.profile.username,
            analyzed_posts,
        )
        
        # Merge flags into posts
        flagged_indices = {f["index"] for f in flagged}
        flagged_reasons = {f["index"]: f["reason"] for f in flagged}
        
        for post in analyzed_posts:
            post["flagged"] = post["index"] in flagged_indices
            post["flag_reason"] = flagged_reasons.get(post["index"], "")
        
        # Sort: flagged first, then by date
        analyzed_posts.sort(key=lambda p: (not p["flagged"], p["date"]), reverse=True)
        
        logger.info(f"  Analysis complete: {len(flagged)} posts flagged")
        
        return AnalysisResult(
            username=result.profile.username,
            profile=self._profile_to_dict(result.profile),
            summary=summary,
            posts=analyzed_posts,
            flagged_count=len(flagged),
            total_posts=len(result.posts),
            total_stories=len(result.stories),
        )
    
    def _analyze_image(self, image_path: Path) -> str:
        """Analyze an image with Gemini Vision"""
        try:
            img = Image.open(image_path)
            response = self.vision_model.generate_content(
                [self.IMAGE_PROMPT, img],
                generation_config=genai.GenerationConfig(
                    max_output_tokens=1024,
                )
            )
            return response.text.strip()
        except Exception as e:
            logger.warning(f"  Image analysis failed: {e}")
            return ""
    
    def _analyze_video(self, video_path: Path) -> str:
        """Analyze a video with Gemini - upload, process, analyze"""
        try:
            # Upload video to Gemini
            logger.info(f"    Uploading video ({video_path.stat().st_size / 1024 / 1024:.1f} MB)...")
            video_file = genai.upload_file(video_path)
            
            # Wait for processing
            logger.info(f"    Waiting for Gemini to process video...")
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED":
                logger.warning(f"    Video processing failed")
                return ""
            
            # Analyze
            logger.info(f"    Analyzing video content...")
            response = self.vision_model.generate_content(
                [video_file, self.VIDEO_PROMPT],
                generation_config=genai.GenerationConfig(
                    max_output_tokens=4096,
                )
            )
            
            # Cleanup uploaded file
            try:
                genai.delete_file(video_file.name)
            except:
                pass
            
            return response.text.strip()
            
        except Exception as e:
            logger.warning(f"  Video analysis failed: {e}")
            return ""
    
    def _run_analysis(
        self,
        username: str,
        posts: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Run comprehensive analysis on all posts"""
        try:
            # Build content for analysis
            content_for_analysis = []
            for p in posts:
                content_for_analysis.append({
                    "index": p["index"],
                    "date": p["date"],
                    "is_story": p["is_story"],
                    "is_video": p["is_video"],
                    "caption": p["caption"],
                    "media_description": p["media_description"],
                })
            
            prompt = self.ANALYSIS_PROMPT.format(
                username=username,
                total_posts=len(posts),
                posts_data=json.dumps(content_for_analysis, indent=2, ensure_ascii=False),
            )
            
            response = self.model.generate_content(prompt)
            result = self._parse_json_response(response.text)
            
            summary = result.get("summary", "")
            flagged = result.get("flagged", [])
            
            return summary, flagged
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return "", []
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from Gemini response"""
        try:
            # Try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        
        # Try finding JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        
        logger.warning(f"Failed to parse JSON response: {text[:200]}...")
        return {}
    
    def _profile_to_dict(self, profile: InstagramProfile) -> Dict[str, Any]:
        """Convert profile to dict"""
        return {
            "username": profile.username,
            "full_name": profile.full_name,
            "bio": profile.bio,
            "followers": profile.followers,
            "following": profile.following,
            "post_count": profile.post_count,
        }

