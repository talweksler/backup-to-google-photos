"""File upload functionality for Google Photos backup tool"""

import os
import logging
from typing import Optional, Tuple, List
import time
import urllib.parse
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import requests

from config import (
    is_supported_file, is_image_file, is_video_file, get_max_file_size,
    MAX_RETRIES, RETRY_DELAY, BACKOFF_FACTOR, UPLOAD_CHUNK_SIZE
)
from safe_logging import safe_log
from state_manager import BackupState
from quota_tracker import QuotaTracker

logger = logging.getLogger(__name__)

class UploadResult:
    """Result of a file upload operation"""
    
    def __init__(self, success: bool, media_item_id: Optional[str] = None, 
                 error_message: Optional[str] = None, skip_reason: Optional[str] = None):
        self.success = success
        self.media_item_id = media_item_id
        self.error_message = error_message
        self.skip_reason = skip_reason

class MediaUploader:
    """Handles uploading media files to Google Photos"""
    
    def __init__(self, service, state: BackupState, quota_tracker: QuotaTracker):
        self.service = service
        self.state = state
        self.quota = quota_tracker
        self.total_files_to_upload = 0  # Set by set_total_files_count method
    
    def set_total_files_count(self, total_files: int):
        """Set the total number of files to upload for progress tracking"""
        self.total_files_to_upload = total_files
    
    def upload_file(self, file_path: str, album_id: Optional[str] = None) -> UploadResult:
        """
        Upload a single file to Google Photos.
        
        Args:
            file_path: Path to the file to upload
            album_id: Optional album ID to add the media to
            
        Returns:
            UploadResult with success status and details
        """
        try:
            # Validate file
            validation_result = self._validate_file(file_path)
            if not validation_result.success:
                return validation_result
            
            # Check if already uploaded
            if self.state.is_file_uploaded(file_path):
                logger.debug(f"File already uploaded, skipping: {file_path}")
                return UploadResult(success=True, skip_reason="Already uploaded")
            
            # Check quota before upload
            can_perform, reason = self.quota.can_perform_operation("upload_file")
            if not can_perform:
                logger.error(f"Cannot upload file {file_path}: {reason}")
                return UploadResult(success=False, error_message=f"Quota limit: {reason}")
            
            # Calculate remaining files
            uploaded_count = len(self.state.get_uploaded_files())
            remaining_files = max(0, self.total_files_to_upload - uploaded_count) if self.total_files_to_upload > 0 else 0
            
            if self.total_files_to_upload > 0:
                logger.info(f"Uploading: {os.path.basename(file_path)} ({self._format_file_size(file_path)}) - {remaining_files:,} files remaining")
            else:
                logger.info(f"Uploading: {os.path.basename(file_path)} ({self._format_file_size(file_path)})")
            
            # Step 1: Upload file bytes
            upload_token = self._upload_bytes(file_path)
            if not upload_token:
                return UploadResult(success=False, error_message="Failed to upload file bytes")
            
            # Step 2: Create media item
            media_item_id = self._create_media_item(file_path, upload_token, album_id)
            if not media_item_id:
                return UploadResult(success=False, error_message="Failed to create media item")
            
            # Mark as uploaded in state
            self.state.mark_file_uploaded(file_path, media_item_id, album_id)
            
            safe_log('info', f"✅ Successfully uploaded: {os.path.basename(file_path)}")
            return UploadResult(success=True, media_item_id=media_item_id)
            
        except Exception as e:
            error_msg = f"Unexpected error uploading {file_path}: {e}"
            logger.error(error_msg)
            return UploadResult(success=False, error_message=error_msg)
    
    def _validate_file(self, file_path: str) -> UploadResult:
        """Validate that a file can be uploaded"""
        # Check if file exists
        if not os.path.exists(file_path):
            return UploadResult(success=False, error_message="File does not exist")
        
        if not os.path.isfile(file_path):
            return UploadResult(success=False, error_message="Path is not a file")
        
        # Check if file format is supported
        if not is_supported_file(file_path):
            return UploadResult(success=True, skip_reason="Unsupported file format")
        
        # Check file size
        try:
            file_size = os.path.getsize(file_path)
            max_size = get_max_file_size(file_path)
            
            if file_size == 0:
                return UploadResult(success=True, skip_reason="Empty file")
            
            if file_size > max_size:
                size_str = self._format_size(file_size)
                max_str = self._format_size(max_size)
                return UploadResult(success=True, skip_reason=f"File too large: {size_str} > {max_str}")
                
        except OSError as e:
            return UploadResult(success=False, error_message=f"Cannot access file: {e}")
        
        return UploadResult(success=True)
    
    def _upload_bytes(self, file_path: str, retries: int = MAX_RETRIES) -> Optional[str]:
        """
        Upload file bytes to Google Photos.
        Returns upload token if successful, None otherwise.
        """
        for attempt in range(retries + 1):
            try:
                logger.debug(f"Uploading bytes for {file_path} (attempt {attempt + 1})")
                
                # Determine MIME type
                mime_type = self._get_mime_type(file_path)
                
                # Create the upload URL
                upload_url = "https://photoslibrary.googleapis.com/v1/uploads"
                
                # Refresh token if needed
                if self.service._http.credentials.expired:
                    logger.debug("Token expired, refreshing...")
                    try:
                        from google.auth.transport.requests import Request
                        self.service._http.credentials.refresh(Request())
                        logger.debug("Token refreshed successfully")
                    except Exception as e:
                        logger.error(f"Failed to refresh token: {e}")
                        return None
                
                # Prepare headers
                # Encode filename properly for HTTP headers (use UTF-8 and URL encode)
                filename = os.path.basename(file_path)
                encoded_filename = urllib.parse.quote(filename.encode('utf-8'))
                
                headers = {
                    'Authorization': f'Bearer {self.service._http.credentials.token}',
                    'Content-type': 'application/octet-stream',
                    'X-Goog-Upload-File-Name': encoded_filename,
                    'X-Goog-Upload-Protocol': 'raw',
                }
                
                # Upload file data
                with open(file_path, 'rb') as f:
                    response = requests.post(upload_url, headers=headers, data=f)
                
                # Note: Bytes upload doesn't count toward Google Photos API quota
                # Only the batchCreate call counts
                
                if response.status_code == 200:
                    upload_token = response.text
                    logger.debug(f"Successfully uploaded bytes, token: {upload_token[:20]}...")
                    return upload_token
                elif response.status_code == 429:  # Rate limit
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    logger.warning(f"Rate limited uploading bytes, waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif response.status_code == 401:  # Authentication error
                    logger.warning(f"Authentication error (attempt {attempt + 1}), trying to refresh token...")
                    try:
                        from google.auth.transport.requests import Request
                        self.service._http.credentials.refresh(Request())
                        logger.info("Token refreshed due to 401 error")
                        # Don't sleep, just retry immediately with new token
                    except Exception as e:
                        logger.error(f"Failed to refresh token after 401 error: {e}")
                        if attempt < retries:
                            wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                            time.sleep(wait_time)
                else:
                    logger.error(f"Upload bytes failed: {response.status_code} - {response.text}")
                    if attempt < retries:
                        wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                        time.sleep(wait_time)
                    
            except Exception as e:
                logger.error(f"Error uploading bytes (attempt {attempt + 1}): {e}")
                if attempt < retries:
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    time.sleep(wait_time)
        
        logger.error(f"Failed to upload bytes for {file_path} after {retries + 1} attempts")
        return None
    
    def _create_media_item(self, file_path: str, upload_token: str, 
                          album_id: Optional[str] = None, retries: int = MAX_RETRIES) -> Optional[str]:
        """
        Create a media item from uploaded bytes.
        Returns media item ID if successful, None otherwise.
        """
        for attempt in range(retries + 1):
            try:
                logger.debug(f"Creating media item for {file_path} (attempt {attempt + 1})")
                
                # Prepare the request body
                filename = os.path.basename(file_path)
                new_media_item = {
                    'description': filename,
                    'simpleMediaItem': {
                        'uploadToken': upload_token,
                        'fileName': filename
                    }
                }
                
                request_body = {
                    'newMediaItems': [new_media_item]
                }
                
                # If album_id is provided, add it to the request
                if album_id:
                    request_body['albumId'] = album_id
                
                response = self.service.mediaItems().batchCreate(body=request_body).execute()
                
                # Record the API request
                if not self.quota.record_requests(1):
                    logger.error("Quota exhausted during media item creation")
                    return None
                
                # Check the response
                if 'newMediaItemResults' in response:
                    for result in response['newMediaItemResults']:
                        status = result.get('status', {})
                        # Check for success: either code=0 or message='Success'
                        is_success = (status.get('code') == 0 or 
                                    status.get('message') == 'Success' or
                                    'mediaItem' in result)  # If mediaItem exists, it's successful
                        
                        if is_success:
                            media_item = result.get('mediaItem', {})
                            media_item_id = media_item.get('id')
                            if media_item_id:
                                logger.debug(f"Successfully created media item: {media_item_id}")
                                return media_item_id
                        else:
                            error_msg = status.get('message', 'Unknown error')
                            logger.error(f"Failed to create media item: {error_msg}")
                
                logger.error(f"No successful media item creation in response: {response}")
                
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    logger.warning(f"Rate limited creating media item, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error creating media item (attempt {attempt + 1}): {e}")
                    if attempt < retries:
                        wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                        time.sleep(wait_time)
                        
            except Exception as e:
                logger.error(f"Error creating media item (attempt {attempt + 1}): {e}")
                if attempt < retries:
                    wait_time = RETRY_DELAY * (BACKOFF_FACTOR ** attempt)
                    time.sleep(wait_time)
        
        logger.error(f"Failed to create media item for {file_path} after {retries + 1} attempts")
        return None
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type for a file"""
        extension = os.path.splitext(file_path)[1].lower()
        
        # Image MIME types
        if extension in ['.jpg', '.jpeg']:
            return 'image/jpeg'
        elif extension == '.png':
            return 'image/png'
        elif extension == '.gif':
            return 'image/gif'
        elif extension == '.bmp':
            return 'image/bmp'
        elif extension == '.webp':
            return 'image/webp'
        elif extension in ['.heic', '.heif']:
            return 'image/heic'
        
        # Video MIME types
        elif extension == '.mp4':
            return 'video/mp4'
        elif extension == '.mov':
            return 'video/quicktime'
        elif extension == '.avi':
            return 'video/x-msvideo'
        elif extension == '.mkv':
            return 'video/x-matroska'
        elif extension == '.m4v':
            return 'video/x-m4v'
        elif extension == '.webm':
            return 'video/webm'
        elif extension == '.3gp':
            return 'video/3gpp'
        
        # Default
        return 'application/octet-stream'
    
    def _format_file_size(self, file_path: str) -> str:
        """Format file size for display"""
        try:
            size = os.path.getsize(file_path)
            return self._format_size(size)
        except:
            return "unknown size"
    
    def _format_size(self, size: int) -> str:
        """Format size in bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def upload_directory_files(self, directory_path: str, album_id: Optional[str] = None) -> Tuple[int, int, int]:
        """
        Upload all supported files in a directory.
        
        Args:
            directory_path: Path to directory to upload
            album_id: Optional album ID to add files to
            
        Returns:
            Tuple of (uploaded_count, skipped_count, failed_count)
        """
        uploaded_count = 0
        skipped_count = 0
        failed_count = 0
        
        try:
            # Get all files in directory
            if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
                safe_log('error', f"Directory does not exist: {directory_path}")
                return 0, 0, 1
            
            files = []
            try:
                for filename in os.listdir(directory_path):
                    file_path = os.path.join(directory_path, filename)
                    if os.path.isfile(file_path):
                        files.append(file_path)
            except PermissionError:
                safe_log('error', f"Permission denied accessing directory: {directory_path}")
                return 0, 0, 1
            
            # Filter to supported files
            supported_files = [f for f in files if is_supported_file(f)]
            
            if not supported_files:
                safe_log('info', f"No supported media files found in: {directory_path}")
                return 0, len(files), 0
            
            safe_log('info', f"Found {len(supported_files)} supported files in: {directory_path}")
            
            # Upload each file
            for file_path in supported_files:
                # Check if we can continue (quota check)
                can_continue, reason = self.quota.can_perform_operation("upload_file")
                if not can_continue:
                    logger.warning(f"Stopping uploads: {reason}")
                    self.state.set_stop_reason(reason)
                    break
                
                result = self.upload_file(file_path, album_id)
                self.state.increment_files_processed()
                
                if result.success:
                    if result.skip_reason:
                        logger.debug(f"Skipped {os.path.basename(file_path)}: {result.skip_reason}")
                        skipped_count += 1
                    else:
                        uploaded_count += 1
                else:
                    logger.error(f"Failed to upload {os.path.basename(file_path)}: {result.error_message}")
                    self.state.mark_file_failed(file_path, result.error_message or "Unknown error")
                    failed_count += 1
                
                # Save state after each file
                self.state.save_state()
            
            logger.info(f"Directory upload complete: {uploaded_count} uploaded, {skipped_count} skipped, {failed_count} failed")
            return uploaded_count, skipped_count, failed_count
            
        except Exception as e:
            safe_log('error', f"Error uploading directory {directory_path}: {e}")
            return uploaded_count, skipped_count, failed_count + 1

def get_directory_media_count(directory_path: str) -> Tuple[int, int]:
    """
    Get count of media files in a directory.
    Returns (total_files, supported_files)
    """
    try:
        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            return 0, 0
        
        total_files = 0
        supported_files = 0
        
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path):
                total_files += 1
                if is_supported_file(file_path):
                    supported_files += 1
        
        return total_files, supported_files
        
    except Exception as e:
        safe_log('error', f"Error counting files in {directory_path}: {e}")
        return 0, 0

if __name__ == "__main__":
    # Test uploader
    logging.basicConfig(level=logging.INFO)
    
    from auth import get_authenticated_service
    from state_manager import BackupState
    from quota_tracker import QuotaTracker
    
    test_dir = "/tmp/test_upload"
    print(f"Testing uploader for directory: {test_dir}")
    
    service = get_authenticated_service()
    if not service:
        print("❌ Failed to authenticate")
        exit(1)
    
    state = BackupState(test_dir)
    state.start_new_session()
    
    quota = QuotaTracker(state, max_session_requests=50)
    uploader = MediaUploader(service, state, quota)
    
    # Test directory counting
    total, supported = get_directory_media_count(test_dir)
    print(f"Directory has {supported}/{total} supported media files")
    
    state.save_state()