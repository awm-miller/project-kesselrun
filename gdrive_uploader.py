"""
Google Drive Uploader - Upload analysis results and media to Google Drive

Uses service account authentication for automated VPS deployment.
Folder structure: user/STORIES/YYYY-MM-DD/ and user/POSTS/YYYY-MM-DD/
"""
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger("gdrive")


class GoogleDriveUploader:
    """Upload files to Google Drive using service account"""
    
    # Use full drive scope to support Shared Drives properly
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(self, service_account_path: str, root_folder_id: Optional[str] = None):
        """
        Initialize Google Drive uploader
        
        Args:
            service_account_path: Path to service account JSON file
            root_folder_id: Shared Drive or folder ID (REQUIRED for service accounts)
        """
        self.service_account_path = Path(service_account_path)
        self.root_folder_id = root_folder_id
        self.service = None
        self._folder_cache: Dict[str, str] = {}  # Cache folder IDs
        self._is_shared_drive = False
        
        self._authenticate()
        
        # Check if root_folder_id is a Shared Drive
        if self.root_folder_id:
            self._check_if_shared_drive()
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        try:
            if not self.service_account_path.exists():
                raise FileNotFoundError(f"Service account file not found: {self.service_account_path}")
            
            credentials = service_account.Credentials.from_service_account_file(
                str(self.service_account_path),
                scopes=self.SCOPES
            )
            
            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive authentication successful")
            
        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            raise
    
    def _check_if_shared_drive(self):
        """Check if root_folder_id is a Shared Drive and set flag"""
        try:
            # Try to get it as a Shared Drive first
            drive = self.service.drives().get(driveId=self.root_folder_id).execute()
            self._is_shared_drive = True
            logger.info(f"Using Shared Drive: {drive.get('name', 'Unknown')}")
        except HttpError:
            # Not a Shared Drive, it's a regular folder
            self._is_shared_drive = False
            logger.info("Using regular folder (not a Shared Drive)")
    
    def _create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """
        Create a folder in Google Drive (or get existing folder ID)
        
        Args:
            folder_name: Name of the folder
            parent_id: Parent folder ID (None for root)
        
        Returns:
            Folder ID
        """
        # Check cache first
        cache_key = f"{parent_id or 'root'}:{folder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]
        
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                # Folder exists
                folder_id = files[0]['id']
                logger.debug(f"Found existing folder: {folder_name} (ID: {folder_id})")
            else:
                # Create new folder
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                if parent_id:
                    file_metadata['parents'] = [parent_id]
                
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
                
                folder_id = folder['id']
                logger.info(f"Created folder: {folder_name} (ID: {folder_id})")
            
            # Cache the result
            self._folder_cache[cache_key] = folder_id
            return folder_id
            
        except HttpError as e:
            logger.error(f"Failed to create/find folder {folder_name}: {e}")
            raise
    
    def _get_folder_path(self, username: str, content_type: str, date_str: str) -> str:
        """
        Get or create the full folder path for content
        
        New structure: user/YYYY-MM-DD/POSTS/ or user/YYYY-MM-DD/STORIES/
        
        Args:
            username: Instagram username
            content_type: 'POSTS' or 'STORIES'
            date_str: Date string YYYY-MM-DD
        
        Returns:
            Folder ID for the final destination
        """
        # Start from root (or specified root folder)
        parent_id = self.root_folder_id
        
        # Create: user/
        user_folder_id = self._create_folder(username, parent_id)
        
        # Create: user/YYYY-MM-DD/
        date_folder_id = self._create_folder(date_str, user_folder_id)
        
        # Create: user/YYYY-MM-DD/POSTS/ or user/YYYY-MM-DD/STORIES/
        type_folder_id = self._create_folder(content_type, date_folder_id)
        
        return type_folder_id
    
    def _get_date_folder(self, username: str, date_str: str) -> str:
        """
        Get or create the date folder for reports
        
        Structure: user/YYYY-MM-DD/
        
        Args:
            username: Instagram username
            date_str: Date string YYYY-MM-DD
        
        Returns:
            Folder ID for the date folder
        """
        parent_id = self.root_folder_id
        user_folder_id = self._create_folder(username, parent_id)
        date_folder_id = self._create_folder(date_str, user_folder_id)
        return date_folder_id
    
    def upload_report(self, local_path: Path, username: str, date_str: str) -> Optional[str]:
        """
        Upload a report file directly to the date folder
        
        Structure: user/YYYY-MM-DD/report.html
        
        Args:
            local_path: Path to local report file
            username: Instagram username
            date_str: Date string YYYY-MM-DD
        
        Returns:
            Google Drive file ID or None if failed
        """
        try:
            if not local_path.exists():
                logger.error(f"Report file not found: {local_path}")
                return None
            
            # Get date folder (user/YYYY-MM-DD/)
            folder_id = self._get_date_folder(username, date_str)
            
            file_metadata = {
                'name': local_path.name,
                'parents': [folder_id]
            }
            
            mime_type = self._get_mime_type(local_path)
            
            media = MediaFileUpload(
                str(local_path),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            logger.info(f"Uploaded report: {local_path.name} to {username}/{date_str}/")
            return file['id']
            
        except HttpError as e:
            logger.error(f"Failed to upload report {local_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error uploading report {local_path}: {e}")
            return None
    
    def upload_file(
        self,
        local_path: Path,
        username: str,
        content_type: str,
        date_str: str,
        filename: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload a file to Google Drive
        
        Args:
            local_path: Path to local file
            username: Instagram username
            content_type: 'POSTS' or 'STORIES' (or 'reports')
            date_str: Date string YYYY-MM-DD
            filename: Optional custom filename (uses original if None)
        
        Returns:
            Google Drive file ID or None if failed
        """
        try:
            if not local_path.exists():
                logger.error(f"File not found: {local_path}")
                return None
            
            # Get destination folder
            folder_id = self._get_folder_path(username, content_type, date_str)
            
            # Prepare file metadata
            file_name = filename or local_path.name
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Determine MIME type
            mime_type = self._get_mime_type(local_path)
            
            # Upload file
            media = MediaFileUpload(
                str(local_path),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            logger.info(f"Uploaded: {file_name} to {username}/{content_type}/{date_str}/")
            return file['id']
            
        except HttpError as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error uploading {local_path}: {e}")
            return None
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Determine MIME type from file extension"""
        ext = file_path.suffix.lower()
        mime_types = {
            '.json': 'application/json',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.mp4': 'video/mp4',
            '.pdf': 'application/pdf',
            '.html': 'text/html',
            '.txt': 'text/plain'
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    def upload_analysis_result(
        self,
        username: str,
        posts: list,
        stories: list,
        date_str: str,
        temp_dir: Path
    ) -> Dict[str, int]:
        """
        Upload all content for an account (JSON + media files)
        
        Args:
            username: Instagram username
            posts: List of analyzed posts (with media_path)
            stories: List of analyzed stories (with media_path)
            date_str: Date string YYYY-MM-DD
            temp_dir: Temporary directory containing downloaded media
        
        Returns:
            Dict with upload statistics
        """
        stats = {
            'posts_json_uploaded': 0,
            'posts_media_uploaded': 0,
            'stories_json_uploaded': 0,
            'stories_media_uploaded': 0,
            'errors': 0
        }
        
        logger.info(f"\nUploading to Google Drive: @{username}")
        
        import json
        
        # Upload posts
        if posts:
            logger.info(f"  Uploading {len(posts)} posts (JSON + media)...")
            for post in posts:
                shortcode = post.get('shortcode', 'unknown')
                
                # Upload media file FIRST (before JSON)
                if 'media_path' in post and post['media_path']:
                    media_path = Path(post['media_path'])
                    if media_path.exists():
                        logger.debug(f"    Uploading media: {media_path.name}")
                        if self.upload_file(media_path, username, 'POSTS', date_str):
                            stats['posts_media_uploaded'] += 1
                        else:
                            logger.warning(f"    Failed to upload media: {media_path.name}")
                            stats['errors'] += 1
                    else:
                        logger.warning(f"    Media file not found: {media_path}")
                
                # Upload JSON metadata
                json_path = temp_dir / username / f"{shortcode}_analysis.json"
                try:
                    json_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(post, f, indent=2, ensure_ascii=False)
                    
                    if self.upload_file(json_path, username, 'POSTS', date_str):
                        stats['posts_json_uploaded'] += 1
                    
                    json_path.unlink()  # Delete after upload
                except Exception as e:
                    logger.error(f"Failed to upload post JSON: {e}")
                    stats['errors'] += 1
        
        # Upload stories
        if stories:
            logger.info(f"  Uploading {len(stories)} stories (JSON + media)...")
            for story in stories:
                shortcode = story.get('shortcode', 'unknown')
                
                # Upload media file FIRST
                if 'media_path' in story and story['media_path']:
                    media_path = Path(story['media_path'])
                    if media_path.exists():
                        logger.debug(f"    Uploading media: {media_path.name}")
                        if self.upload_file(media_path, username, 'STORIES', date_str):
                            stats['stories_media_uploaded'] += 1
                        else:
                            logger.warning(f"    Failed to upload media: {media_path.name}")
                            stats['errors'] += 1
                    else:
                        logger.warning(f"    Media file not found: {media_path}")
                
                # Upload JSON metadata
                json_path = temp_dir / username / f"{shortcode}_story_analysis.json"
                try:
                    json_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(story, f, indent=2, ensure_ascii=False)
                    
                    if self.upload_file(json_path, username, 'STORIES', date_str):
                        stats['stories_json_uploaded'] += 1
                    
                    json_path.unlink()  # Delete after upload
                except Exception as e:
                    logger.error(f"Failed to upload story JSON: {e}")
                    stats['errors'] += 1
                
                # Upload media file
                if 'media_path' in story and story['media_path']:
                    media_path = Path(story['media_path'])
                    if media_path.exists():
                        if self.upload_file(media_path, username, 'STORIES', date_str):
                            stats['stories_media_uploaded'] += 1
                        else:
                            stats['errors'] += 1
        
        logger.info(f"  Upload complete: {stats['posts_json_uploaded']} posts, "
                   f"{stats['stories_json_uploaded']} stories, "
                   f"{stats['errors']} errors")
        
        return stats

