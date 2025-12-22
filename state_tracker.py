"""
State Tracker - Tracks which posts and stories have been analyzed

Maintains state.json to prevent re-analyzing the same content.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime

logger = logging.getLogger("state_tracker")


class StateTracker:
    """Tracks analyzed posts and stories for each account"""
    
    def __init__(self, state_file: str = "state.json"):
        self.state_file = Path(state_file)
        self.state: Dict = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load state from file or create empty state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    logger.info(f"Loaded state for {len(state)} accounts")
                    return state
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
                return {}
        else:
            logger.info("No existing state file - starting fresh")
            return {}
    
    def _save_state(self):
        """Save state to file"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def get_analyzed_posts(self, username: str) -> Set[str]:
        """Get set of analyzed post shortcodes for a user"""
        if username not in self.state:
            return set()
        return set(self.state[username].get("posts", []))
    
    def get_analyzed_stories(self, username: str) -> Set[str]:
        """Get set of analyzed story IDs for a user"""
        if username not in self.state:
            return set()
        return set(self.state[username].get("stories", []))
    
    def get_last_run(self, username: str) -> Optional[str]:
        """Get last run timestamp for a user"""
        if username not in self.state:
            return None
        return self.state[username].get("last_run")
    
    def filter_new_posts(self, username: str, all_posts: List) -> List:
        """
        Filter posts to only those not yet analyzed
        
        Args:
            username: Instagram username
            all_posts: List of InstagramPost objects with 'shortcode' attribute
        
        Returns:
            List of new posts only
        """
        analyzed = self.get_analyzed_posts(username)
        new_posts = [p for p in all_posts if p.shortcode not in analyzed]
        
        if new_posts:
            logger.info(f"@{username}: {len(new_posts)} new posts (out of {len(all_posts)} total)")
        else:
            logger.info(f"@{username}: No new posts (all {len(all_posts)} already analyzed)")
        
        return new_posts
    
    def filter_new_stories(self, username: str, all_stories: List) -> List:
        """
        Filter stories to only those not yet analyzed
        
        Args:
            username: Instagram username
            all_stories: List of InstagramPost objects with 'shortcode' attribute (story ID)
        
        Returns:
            List of new stories only
        """
        analyzed = self.get_analyzed_stories(username)
        new_stories = [s for s in all_stories if s.shortcode not in analyzed]
        
        if new_stories:
            logger.info(f"@{username}: {len(new_stories)} new stories (out of {len(all_stories)} total)")
        else:
            logger.info(f"@{username}: No new stories (all {len(all_stories)} already analyzed)")
        
        return new_stories
    
    def mark_analyzed(
        self,
        username: str,
        post_shortcodes: List[str] = None,
        story_ids: List[str] = None
    ):
        """
        Mark posts/stories as analyzed for a user
        
        Args:
            username: Instagram username
            post_shortcodes: List of post shortcodes to mark as analyzed
            story_ids: List of story IDs to mark as analyzed
        """
        if username not in self.state:
            self.state[username] = {
                "posts": [],
                "stories": [],
                "last_run": None
            }
        
        # Add new posts (avoiding duplicates)
        if post_shortcodes:
            existing_posts = set(self.state[username]["posts"])
            existing_posts.update(post_shortcodes)
            self.state[username]["posts"] = list(existing_posts)
            logger.info(f"@{username}: Marked {len(post_shortcodes)} posts as analyzed")
        
        # Add new stories (avoiding duplicates)
        if story_ids:
            existing_stories = set(self.state[username]["stories"])
            existing_stories.update(story_ids)
            self.state[username]["stories"] = list(existing_stories)
            logger.info(f"@{username}: Marked {len(story_ids)} stories as analyzed")
        
        # Update last run timestamp
        self.state[username]["last_run"] = datetime.utcnow().isoformat()
        
        # Save to disk
        self._save_state()
    
    def get_stats(self, username: str) -> Dict:
        """Get statistics for a user"""
        if username not in self.state:
            return {
                "total_posts_analyzed": 0,
                "total_stories_analyzed": 0,
                "last_run": None
            }
        
        return {
            "total_posts_analyzed": len(self.state[username].get("posts", [])),
            "total_stories_analyzed": len(self.state[username].get("stories", [])),
            "last_run": self.state[username].get("last_run")
        }
    
    def cleanup_old_stories(self, username: str, max_stories: int = 1000):
        """
        Cleanup old story IDs (stories expire after 24h, so we don't need to track them forever)
        Keep only the most recent N story IDs
        """
        if username not in self.state:
            return
        
        stories = self.state[username].get("stories", [])
        if len(stories) > max_stories:
            # Keep only the most recent ones
            self.state[username]["stories"] = stories[-max_stories:]
            logger.info(f"@{username}: Cleaned up old story tracking (kept {max_stories})")
            self._save_state()

