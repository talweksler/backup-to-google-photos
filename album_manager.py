"""Album management for Google Photos backup tool"""

import logging
from typing import Dict, Optional, List, Tuple
from googleapiclient.errors import HttpError
import time

from config import sanitize_album_name, MAX_RETRIES, RETRY_DELAY, BACKOFF_FACTOR
from state_manager import BackupState
from quota_tracker import QuotaTracker

logger = logging.getLogger(__name__)

class AlbumExistsAction:
    """Actions to take when an album already exists"""
    SKIP = "skip"
    MERGE = "merge"
    STOP = "stop"

class AlbumManager:
    """Manages Google Photos albums"""
    
    def __init__(self, service, state: BackupState, quota_tracker: QuotaTracker):
        self.service = service
        self.state = state
        self.quota = quota_tracker
        self._albums_cache: Optional[Dict[str, str]] = None  # {album_title: album_id}
        self._albums_cache_loaded = False
    
    def load_existing_albums(self) -> bool:
        """
        Load albums created by this app from Google Photos.
        Note: Can only access albums created by this app due to API restrictions.
        Returns True if successful, False if quota exceeded.
        """
        if self._albums_cache_loaded:
            return True
        
        try:
            logger.info("Loading app-created albums from Google Photos...")
            
            # Check quota first
            can_perform, reason = self.quota.can_perform_operation("list_albums", estimated_albums=100)
            if not can_perform:
                logger.error(f"Cannot list albums: {reason}")
                return False
            
            albums = {}
            next_page_token = None
            page_count = 0
            
            while True:
                # Check quota before each request
                if not self.quota.can_make_requests(1):
                    logger.error("Quota exhausted while loading albums")
                    return False
                
                try:
                    request_body = {'pageSize': 50}
                    if next_page_token:
                        request_body['pageToken'] = next_page_token
                    
                    response = self.service.albums().list(**request_body).execute()
                    
                    if not self.quota.record_requests(1):
                        logger.error("Quota exhausted after listing albums")
                        return False
                    
                    page_count += 1
                    logger.debug(f"Loaded albums page {page_count}")
                    
                    # Process albums from this page
                    if 'albums' in response:
                        for album in response['albums']:
                            album_title = album.get('title', '')
                            album_id = album.get('id', '')
                            if album_title and album_id:
                                albums[album_title] = album_id
                    
                    # Check if there are more pages
                    next_page_token = response.get('nextPageToken')
                    if not next_page_token:
                        break
                
                except HttpError as e:
                    if e.resp.status == 429:  # Rate limit
                        logger.warning("Rate limited while loading albums, waiting...")
                        time.sleep(RETRY_DELAY)
                        continue
                    elif e.resp.status == 403:
                        # With new API restrictions, 403 can mean no app-created albums exist yet
                        logger.info("No app-created albums found (expected for first run with new API restrictions)")
                        break
                    else:
                        logger.error(f"HTTP error loading albums: {e}")
                        return False
                
                except Exception as e:
                    logger.error(f"Unexpected error loading albums: {e}")
                    return False
            
            self._albums_cache = albums
            self._albums_cache_loaded = True
            
            logger.info(f"Loaded {len(albums)} existing albums")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load existing albums: {e}")
            return False
    
    def get_existing_albums(self) -> Dict[str, str]:
        """Get cached existing albums"""
        if not self._albums_cache_loaded:
            if not self.load_existing_albums():
                return {}
        
        return self._albums_cache or {}
    
    def album_exists(self, album_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an album exists.
        Returns (exists, album_id_if_exists)
        """
        # First check our created albums cache
        album_id = self.state.get_album_id(album_name)
        if album_id:
            return True, album_id
        
        # Then check existing albums from Google Photos
        existing_albums = self.get_existing_albums()
        album_id = existing_albums.get(album_name)
        
        return album_id is not None, album_id
    
    def create_album(self, album_name: str, retries: int = MAX_RETRIES) -> Optional[str]:
        """
        Create a new album.
        Returns album_id if successful, None if failed.
        """
        sanitized_name = sanitize_album_name(album_name)
        
        if not sanitized_name:
            logger.error(f"Invalid album name: '{album_name}'")
            return None
        
        # Check quota
        can_perform, reason = self.quota.can_perform_operation("create_album")
        if not can_perform:
            logger.error(f"Cannot create album '{sanitized_name}': {reason}")
            return None
        
        for attempt in range(retries + 1):
            try:
                logger.info(f"Creating album: '{sanitized_name}' (attempt {attempt + 1})")
                
                request_body = {
                    'album': {
                        'title': sanitized_name
                    }
                }
                
                response = self.service.albums().create(body=request_body).execute()
                
                if not self.quota.record_requests(1):
                    logger.error("Quota exhausted after creating album")
                    return None
                
                album_id = response.get('id')
                if album_id:
                    logger.info(f"Successfully created album: '{sanitized_name}' (ID: {album_id})")
                    
                    # Cache the created album
                    self.state.add_created_album(sanitized_name, album_id)
                    if self._albums_cache is not None:
                        self._albums_cache[sanitized_name] = album_id
                    
                    return album_id
                else:
                    logger.error(f"No album ID in response: {response}")
                    return None
                
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    logger.warning(f"Rate limited creating album, waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif e.resp.status == 409:  # Conflict - album might already exist
                    logger.warning(f"Album '{sanitized_name}' might already exist")
                    # Try to find it
                    exists, album_id = self.album_exists(sanitized_name)
                    if exists and album_id:
                        logger.info(f"Found existing album: '{sanitized_name}' (ID: {album_id})")
                        self.state.add_created_album(sanitized_name, album_id)
                        return album_id
                    else:
                        logger.error(f"Album conflict but couldn't find existing album")
                        return None
                else:
                    logger.error(f"HTTP error creating album '{sanitized_name}': {e}")
                    if attempt < retries:
                        wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                        time.sleep(wait_time)
                    else:
                        return None
                        
            except Exception as e:
                logger.error(f"Unexpected error creating album '{sanitized_name}': {e}")
                if attempt < retries:
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    time.sleep(wait_time)
                else:
                    return None
        
        logger.error(f"Failed to create album '{sanitized_name}' after {retries + 1} attempts")
        return None
    
    def get_or_create_album(self, album_name: str, 
                           exists_action: str = AlbumExistsAction.STOP) -> Tuple[Optional[str], bool]:
        """
        Get existing album or create new one based on policy.
        Returns (album_id, created_new)
        """
        sanitized_name = sanitize_album_name(album_name)
        
        if not sanitized_name:
            logger.error(f"Invalid album name: '{album_name}'")
            return None, False
        
        # Check if album exists
        exists, album_id = self.album_exists(sanitized_name)
        
        if exists and album_id:
            logger.info(f"Album '{sanitized_name}' already exists (ID: {album_id})")
            
            if exists_action == AlbumExistsAction.SKIP:
                logger.info(f"Skipping existing album: '{sanitized_name}'")
                return None, False
            elif exists_action == AlbumExistsAction.MERGE:
                logger.info(f"Using existing album: '{sanitized_name}'")
                # Make sure it's in our state
                self.state.add_created_album(sanitized_name, album_id)
                return album_id, False
            else:  # STOP
                logger.error(f"Album '{sanitized_name}' already exists. Use --skip-existing or --merge-existing flags.")
                return None, False
        else:
            # Album doesn't exist, create it
            album_id = self.create_album(sanitized_name)
            if album_id:
                return album_id, True
            else:
                return None, False
    
    def add_media_to_album(self, album_id: str, media_item_ids: List[str], 
                          retries: int = MAX_RETRIES) -> bool:
        """
        Add media items to an album.
        Returns True if successful, False otherwise.
        """
        if not media_item_ids:
            logger.warning("No media items to add to album")
            return True
        
        # Check quota
        can_perform, reason = self.quota.can_perform_operation("add_to_album")
        if not can_perform:
            logger.error(f"Cannot add media to album: {reason}")
            return False
        
        for attempt in range(retries + 1):
            try:
                logger.debug(f"Adding {len(media_item_ids)} media items to album (attempt {attempt + 1})")
                
                request_body = {
                    'mediaItemIds': media_item_ids
                }
                
                response = self.service.albums().batchAddMediaItems(
                    albumId=album_id, 
                    body=request_body
                ).execute()
                
                if not self.quota.record_requests(1):
                    logger.error("Quota exhausted after adding media to album")
                    return False
                
                # Check for any errors in the response
                if 'newMediaItemResults' in response:
                    success_count = 0
                    for result in response['newMediaItemResults']:
                        if result.get('status', {}).get('code') == 0:  # SUCCESS
                            success_count += 1
                        else:
                            error_msg = result.get('status', {}).get('message', 'Unknown error')
                            logger.warning(f"Failed to add media item: {error_msg}")
                    
                    if success_count > 0:
                        logger.info(f"Successfully added {success_count}/{len(media_item_ids)} media items to album")
                        return success_count == len(media_item_ids)
                
                logger.info(f"Successfully added {len(media_item_ids)} media items to album")
                return True
                
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    logger.warning(f"Rate limited adding media to album, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error adding media to album: {e}")
                    if attempt < retries:
                        wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                        time.sleep(wait_time)
                    else:
                        return False
                        
            except Exception as e:
                logger.error(f"Unexpected error adding media to album: {e}")
                if attempt < retries:
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    time.sleep(wait_time)
                else:
                    return False
        
        logger.error(f"Failed to add media to album after {retries + 1} attempts")
        return False
    
    def get_albums_summary(self) -> str:
        """Get human-readable summary of albums"""
        created_albums = self.state.get_created_albums()
        existing_albums = self.get_existing_albums()
        
        lines = [
            f"📁 Album Summary:",
            f"   Created in this backup: {len(created_albums)}",
            f"   Total existing albums: {len(existing_albums)}"
        ]
        
        if created_albums:
            lines.append("   Albums created:")
            for name, album_id in created_albums.items():
                lines.append(f"     • {name} ({album_id})")
        
        return "\n".join(lines)

if __name__ == "__main__":
    # Test album management
    logging.basicConfig(level=logging.INFO)
    
    from auth import get_authenticated_service
    from state_manager import BackupState
    from quota_tracker import QuotaTracker
    
    test_dir = "/tmp/test_albums"
    print(f"Testing album management for directory: {test_dir}")
    
    service = get_authenticated_service()
    if not service:
        print("❌ Failed to authenticate")
        exit(1)
    
    state = BackupState(test_dir)
    state.start_new_session()
    
    quota = QuotaTracker(state, max_session_requests=50)
    album_mgr = AlbumManager(service, state, quota)
    
    print("Loading existing albums...")
    if album_mgr.load_existing_albums():
        print("✅ Albums loaded successfully")
        print(album_mgr.get_albums_summary())
    else:
        print("❌ Failed to load albums")
    
    state.save_state()