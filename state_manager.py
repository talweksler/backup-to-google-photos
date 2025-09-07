"""State management for Google Photos backup tool"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set, List
import logging

from config import (
    get_state_filepath, STATE_VERSION, ensure_directories_exist
)
from safe_logging import safe_log

logger = logging.getLogger(__name__)

class BackupState:
    """Manages the backup state for a specific directory"""
    
    def __init__(self, base_directory: str):
        self.base_directory = os.path.abspath(base_directory)
        self.state_file = get_state_filepath(self.base_directory)
        self.state_data = self._load_or_create_state()
    
    def _load_or_create_state(self) -> Dict[str, Any]:
        """Load existing state or create new state structure"""
        ensure_directories_exist()
        
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                # Validate state structure
                if self._validate_state(state):
                    logger.info(f"Loaded existing state from {self.state_file}")
                    return state
                else:
                    logger.warning(f"Invalid state file structure, creating new state")
                    return self._create_new_state()
                    
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning(f"Failed to load state file: {e}, creating new state")
                return self._create_new_state()
        else:
            logger.info(f"No existing state file, creating new state")
            return self._create_new_state()
    
    def _validate_state(self, state: Dict[str, Any]) -> bool:
        """Validate state file structure"""
        required_keys = [
            'base_directory', 'state_version', 'created_at', 
            'current_session', 'uploaded_files', 'failed_uploads', 'created_albums'
        ]
        
        if not all(key in state for key in required_keys):
            return False
        
        # Check if base directory matches
        if state.get('base_directory') != self.base_directory:
            logger.warning(f"State file base directory mismatch: {state.get('base_directory')} != {self.base_directory}")
            return False
        
        return True
    
    def _create_new_state(self) -> Dict[str, Any]:
        """Create a new state structure"""
        now = datetime.now(timezone.utc).isoformat()
        
        return {
            'base_directory': self.base_directory,
            'state_version': STATE_VERSION,
            'created_at': now,
            'last_updated': now,
            'current_session': {
                'start_time': now,
                'api_requests_count': 0,
                'last_processed_directory': None,
                'stop_reason': None,
                'files_processed': 0,
                'files_uploaded': 0,
                'files_failed': 0
            },
            'daily_quota': {
                'date': datetime.now(timezone.utc).date().isoformat(),
                'total_requests': 0
            },
            'uploaded_files': {},
            'failed_uploads': {},
            'created_albums': {}
        }
    
    def save_state(self):
        """Save current state to file"""
        try:
            self.state_data['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            # Write state file atomically
            temp_file = self.state_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.state_data, f, indent=2, ensure_ascii=False)
            
            # Atomic move
            os.replace(temp_file, self.state_file)
            logger.debug(f"State saved to {self.state_file}")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def start_new_session(self):
        """Start a new backup session"""
        now = datetime.now(timezone.utc).isoformat()
        
        self.state_data['current_session'] = {
            'start_time': now,
            'api_requests_count': 0,
            'last_processed_directory': None,
            'stop_reason': None,
            'files_processed': 0,
            'files_uploaded': 0,
            'files_failed': 0
        }
        
        # Update daily quota if it's a new day
        today = datetime.now(timezone.utc).date().isoformat()
        if self.state_data['daily_quota']['date'] != today:
            self.state_data['daily_quota'] = {
                'date': today,
                'total_requests': 0
            }
        
        self.save_state()
        logger.info("Started new backup session")
    
    def add_api_request(self, count: int = 1):
        """Add to API request count"""
        self.state_data['current_session']['api_requests_count'] += count
        self.state_data['daily_quota']['total_requests'] += count
        
    def set_last_processed_directory(self, directory: str):
        """Set the last processed directory"""
        self.state_data['current_session']['last_processed_directory'] = directory
    
    def mark_file_uploaded(self, file_path: str, media_item_id: str, album_id: Optional[str] = None):
        """Mark a file as successfully uploaded"""
        now = datetime.now(timezone.utc).isoformat()
        
        self.state_data['uploaded_files'][file_path] = {
            'uploaded_at': now,
            'media_item_id': media_item_id,
            'album_id': album_id
        }
        
        self.state_data['current_session']['files_uploaded'] += 1
        
        # Remove from failed uploads if it was there
        if file_path in self.state_data['failed_uploads']:
            del self.state_data['failed_uploads'][file_path]
    
    def mark_file_failed(self, file_path: str, error_message: str, attempts: int = 1):
        """Mark a file as failed to upload"""
        now = datetime.now(timezone.utc).isoformat()
        
        if file_path in self.state_data['failed_uploads']:
            # Update existing failed entry
            self.state_data['failed_uploads'][file_path]['attempts'] += attempts
            self.state_data['failed_uploads'][file_path]['last_attempt'] = now
            self.state_data['failed_uploads'][file_path]['error'] = error_message
        else:
            # Create new failed entry
            self.state_data['failed_uploads'][file_path] = {
                'error': error_message,
                'attempts': attempts,
                'last_attempt': now,
                'first_attempt': now
            }
        
        self.state_data['current_session']['files_failed'] += 1
    
    def increment_files_processed(self):
        """Increment the count of files processed"""
        self.state_data['current_session']['files_processed'] += 1
    
    def add_created_album(self, album_name: str, album_id: str):
        """Add a created album to state"""
        self.state_data['created_albums'][album_name] = album_id
    
    def set_stop_reason(self, reason: str):
        """Set the reason why the backup stopped"""
        self.state_data['current_session']['stop_reason'] = reason
        safe_log('info', f"Backup stopped: {reason}")
    
    def is_file_uploaded(self, file_path: str) -> bool:
        """Check if a file was already uploaded"""
        return file_path in self.state_data['uploaded_files']
    
    def get_uploaded_files(self) -> Set[str]:
        """Get set of all uploaded file paths"""
        return set(self.state_data['uploaded_files'].keys())
    
    def get_failed_files(self) -> Dict[str, Dict[str, Any]]:
        """Get dictionary of failed files and their error info"""
        return self.state_data['failed_uploads'].copy()
    
    def get_created_albums(self) -> Dict[str, str]:
        """Get dictionary of created albums {name: album_id}"""
        return self.state_data['created_albums'].copy()
    
    def get_album_id(self, album_name: str) -> Optional[str]:
        """Get album ID for a given album name"""
        return self.state_data['created_albums'].get(album_name)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics"""
        return self.state_data['current_session'].copy()
    
    def get_daily_quota_usage(self) -> int:
        """Get today's total API request count"""
        return self.state_data['daily_quota']['total_requests']
    
    def get_session_request_count(self) -> int:
        """Get current session's API request count"""
        return self.state_data['current_session']['api_requests_count']
    
    def get_last_processed_directory(self) -> Optional[str]:
        """Get the last processed directory"""
        return self.state_data['current_session'].get('last_processed_directory')
    
    def clear_failed_files(self):
        """Clear the failed files list (for retry attempts)"""
        self.state_data['failed_uploads'] = {}
        logger.info("Cleared failed files list")
    
    def delete_state_file(self):
        """Delete the state file (for fresh start)"""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                logger.info(f"Deleted state file: {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to delete state file: {e}")
    
    def get_summary(self) -> str:
        """Get a human-readable summary of the current state"""
        stats = self.get_session_stats()
        daily_quota = self.get_daily_quota_usage()
        
        summary_parts = [
            f"Base directory: {self.base_directory}",
            f"Session started: {stats.get('start_time', 'Unknown')}",
            f"Files processed: {stats.get('files_processed', 0)}",
            f"Files uploaded: {stats.get('files_uploaded', 0)}",
            f"Files failed: {stats.get('files_failed', 0)}",
            f"API requests (session): {stats.get('api_requests_count', 0)}",
            f"API requests (daily): {daily_quota}",
            f"Albums created: {len(self.state_data['created_albums'])}"
        ]
        
        last_dir = stats.get('last_processed_directory')
        if last_dir:
            summary_parts.append(f"Last processed: {last_dir}")
        
        stop_reason = stats.get('stop_reason')
        if stop_reason:
            summary_parts.append(f"Stop reason: {stop_reason}")
        
        return "\n".join(summary_parts)

def list_all_states() -> List[str]:
    """List all existing state files"""
    ensure_directories_exist()
    
    from config import STATE_DIR, STATE_FILE_PREFIX, STATE_FILE_SUFFIX
    
    states = []
    try:
        for filename in os.listdir(STATE_DIR):
            if filename.startswith(STATE_FILE_PREFIX) and filename.endswith(STATE_FILE_SUFFIX):
                state_path = os.path.join(STATE_DIR, filename)
                states.append(state_path)
    except FileNotFoundError:
        pass
    
    return states

if __name__ == "__main__":
    # Test state management
    logging.basicConfig(level=logging.INFO)
    
    test_dir = "/tmp/test_photos"
    print(f"Testing state management for directory: {test_dir}")
    
    state = BackupState(test_dir)
    state.start_new_session()
    
    print("State summary:")
    print(state.get_summary())
    
    # Test operations
    state.add_api_request(5)
    state.set_last_processed_directory("/tmp/test_photos/subfolder")
    state.mark_file_uploaded("/tmp/test_photos/image1.jpg", "media123", "album456")
    state.mark_file_failed("/tmp/test_photos/image2.jpg", "Upload failed", 1)
    state.add_created_album("Test Album", "album456")
    
    print("\nAfter test operations:")
    print(state.get_summary())
    
    state.save_state()
    print(f"\nState saved to: {state.state_file}")