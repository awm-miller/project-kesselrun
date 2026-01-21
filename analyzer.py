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
    
    # Prompt for video transcript ONLY (Call 1)
    TRANSCRIPT_PROMPT = """IMPORTANT: Do NOT start with phrases like "Okay", "Here is", etc. Begin directly with the transcript.

TRANSCRIBE all speech and audio from this video. Include:
- All spoken words (verbatim)
- Any song lyrics or music with lyrics
- Text that appears on screen that is being read aloud

If there is no speech or audio to transcribe, respond with: [NO SPEECH]

Provide ONLY the transcript, nothing else."""

    # Prompt for flagging analysis (Call 2)
    FLAGGING_PROMPT = """IMPORTANT: Do NOT include any conversational filler, preamble, or phrases like "Okay", "Here is", etc. Start directly with the JSON response.

You are a content moderation analyst reviewing Instagram content from @{username}.

TOTAL ITEMS: {total_posts}
Each item has an INDEX number. Use these indices to identify items.

YOUR TASK: Identify ANY items that should be flagged for review.

FLAG content that contains:
- Antisemitic content or tropes
- Anti-Zionist rhetoric that crosses into hate speech
- Support for proscribed terrorist organisations (Hamas, Hezbollah, PIJ, etc.)
- Glorification of violence or terrorism
- Genuinely hateful, inflammatory, or threatening statements
- Extremist recruitment or propaganda

Do NOT flag:
- Normal political opinions or criticism
- News coverage or factual reporting
- Educational content about these topics

CONTENT TO REVIEW:
{posts_data}

RESPOND WITH VALID JSON ONLY (no markdown, no extra text):
{{
  "summary": "Brief 2-3 sentence summary of the content reviewed and any concerns.",
  "flagged": [
    {{"index": 0, "reason": "Clear, specific reason why this content is problematic"}},
    {{"index": 5, "reason": "Clear, specific reason why this content is problematic"}}
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
        
        # Step 1: Transcribe videos AND upload all media to Google Drive
        upload_msg = " + uploading to Google Drive" if self.gdrive_uploader else ""
        logger.info(f"  Step 1: Processing {len(all_content)} media items{upload_msg}...")
        analyzed_posts = []
        
        for i, post in enumerate(all_content):
            media_type = 'video' if post.is_video else 'photo'
            content_type = 'STORIES' if post.is_story else 'POSTS'
            logger.info(f"  [{i+1}/{len(all_content)}] Processing {media_type}...")
            
            video_transcript = ""
            gdrive_file_id = None
            
            if post.media_path and post.media_path.exists():
                # For videos: transcribe audio (Call 1)
                if post.is_video:
                    video_transcript = self._transcribe_video(post.media_path)
                    if video_transcript:
                        logger.info(f"    ↳ Transcribed: {len(video_transcript)} chars")
                # For images: no analysis needed (flagging uses caption only)
                
                # Upload to Google Drive
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
            
            # Upload story screenshot if available
            gdrive_screenshot_id = None
            if post.is_story and post.screenshot_path and post.screenshot_path.exists():
                if self.gdrive_uploader:
                    try:
                        gdrive_screenshot_id = self.gdrive_uploader.upload_file(
                            local_path=post.screenshot_path,
                            username=result.profile.username,
                            content_type="screenshot",
                            date_str=date_str
                        )
                        if gdrive_screenshot_id:
                            logger.info(f"    ↳ Uploaded screenshot to Google Drive")
                    except Exception as e:
                        logger.warning(f"    ↳ Failed to upload screenshot: {e}")
            
            analyzed_posts.append({
                "index": i,
                "shortcode": post.shortcode,
                "url": post.url,
                "date": post.date.isoformat(),
                "caption": post.caption if post.caption else "",
                "is_video": post.is_video,
                "is_story": post.is_story,
                "likes": post.likes,
                "video_transcript": video_transcript,  # New field: transcript only
                "media_path": str(post.media_path) if post.media_path else None,
                "gdrive_file_id": gdrive_file_id,
                "gdrive_screenshot_id": gdrive_screenshot_id,
            })
        
        # Step 2: Run flagging analysis (Call 2)
        logger.info(f"  Step 2: Running flagging analysis...")
        summary, flagged = self._run_flagging_analysis(
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
    
    def _transcribe_video(self, video_path: Path) -> str:
        """
        Call 1: Transcribe video audio ONLY
        Returns just the speech/audio transcript, no visual description.
        """
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
            
            # Transcribe audio only
            logger.info(f"    Transcribing video audio...")
            response = self.vision_model.generate_content(
                [video_file, self.TRANSCRIPT_PROMPT],
                generation_config=genai.GenerationConfig(
                    max_output_tokens=4096,
                )
            )
            
            # Cleanup uploaded file
            try:
                genai.delete_file(video_file.name)
            except:
                pass
            
            transcript = response.text.strip()
            
            # Handle no speech case
            if transcript == "[NO SPEECH]" or not transcript:
                return ""
            
            return transcript
            
        except Exception as e:
            logger.warning(f"  Video transcription failed: {e}")
            return ""
    
    def _run_flagging_analysis(
        self,
        username: str,
        posts: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Call 2: Run flagging analysis on all posts
        Uses caption + video_transcript to determine what should be flagged.
        """
        try:
            # Build content for flagging analysis
            content_for_analysis = []
            for p in posts:
                item = {
                    "index": p["index"],
                    "date": p["date"],
                    "type": "story" if p["is_story"] else "post",
                    "media_type": "video" if p["is_video"] else "photo",
                    "caption": p["caption"] if p["caption"] else "(no caption)",
                }
                # Include transcript for videos
                if p.get("video_transcript"):
                    item["video_transcript"] = p["video_transcript"]
                
                content_for_analysis.append(item)
            
            prompt = self.FLAGGING_PROMPT.format(
                username=username,
                total_posts=len(posts),
                posts_data=json.dumps(content_for_analysis, indent=2, ensure_ascii=False),
            )
            
            logger.info(f"    Running flagging analysis...")
            response = self.model.generate_content(prompt)
            result = self._parse_json_response(response.text)
            
            summary = result.get("summary", "")
            flagged = result.get("flagged", [])
            
            return summary, flagged
            
        except Exception as e:
            logger.error(f"Flagging analysis failed: {e}")
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

