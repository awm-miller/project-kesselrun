"""
State Tracker - Track analyzed posts and stories to avoid reprocessing
"""
import json
import logging
from pathlib import Path
from typing import Dict, Set, List, Any
from datetime import datetime

logger = logging.getLogger("state_tracker")


class StateTracker:
    """Tracks which posts and stories have been analyzed"""
    
    def __init__(self, state_file: str = "state.json"):
        self.state_file = Path(state_file)
        self.state: Dict[str, Dict[str, Any]] = {}
        self._load_state()
    
    def _load_state(self):
        """Load state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                logger.info(f"Loaded state for {len(self.state)} accounts")
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
                self.state = {}
        else:
            logger.info("No existing state file - starting fresh")
            self.state = {}
    
    def _save_state(self):
        """Save state to file"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _get_account_state(self, username: str) -> Dict[str, Any]:
        """Get or create state for an account"""
        if username not in self.state:
            self.state[username] = {
                'analyzed_posts': [],
                'analyzed_stories': [],
                'last_updated': None
            }
        return self.state[username]
    
    def get_new_posts(self, username: str, posts: List[Any]) -> List[Any]:
        """Filter posts to only return ones not yet analyzed"""
        account_state = self._get_account_state(username)
        analyzed_shortcodes = set(account_state.get('analyzed_posts', []))
        
        new_posts = [p for p in posts if p.shortcode not in analyzed_shortcodes]
        
        logger.info(f"@{username}: {len(new_posts)} new posts (out of {len(posts)} total)")
        return new_posts
    
    def get_new_stories(self, username: str, stories: List[Any]) -> List[Any]:
        """Filter stories to only return ones not yet analyzed"""
        account_state = self._get_account_state(username)
        analyzed_shortcodes = set(account_state.get('analyzed_stories', []))
        
        new_stories = [s for s in stories if s.shortcode not in analyzed_shortcodes]
        
        logger.info(f"@{username}: {len(new_stories)} new stories (out of {len(stories)} total)")
        return new_stories
    
    def mark_posts_analyzed(self, username: str, posts: List[Any]):
        """Mark posts as analyzed"""
        account_state = self._get_account_state(username)
        
        existing = set(account_state.get('analyzed_posts', []))
        for post in posts:
            shortcode = post.get('shortcode') if isinstance(post, dict) else post.shortcode
            existing.add(shortcode)
        
        account_state['analyzed_posts'] = list(existing)
        account_state['last_updated'] = datetime.now().isoformat()
        
        self._save_state()
        logger.info(f"@{username}: Marked {len(posts)} posts as analyzed")
    
    def mark_stories_analyzed(self, username: str, stories: List[Any]):
        """Mark stories as analyzed"""
        account_state = self._get_account_state(username)
        
        existing = set(account_state.get('analyzed_stories', []))
        for story in stories:
            shortcode = story.get('shortcode') if isinstance(story, dict) else story.shortcode
            existing.add(shortcode)
        
        account_state['analyzed_stories'] = list(existing)
        account_state['last_updated'] = datetime.now().isoformat()
        
        self._save_state()
        logger.info(f"@{username}: Marked {len(stories)} stories as analyzed")
    
    def get_stats(self, username: str) -> Dict[str, int]:
        """Get stats for an account"""
        account_state = self._get_account_state(username)
        return {
            'total_posts_tracked': len(account_state.get('analyzed_posts', [])),
            'total_stories_tracked': len(account_state.get('analyzed_stories', []))
        }

