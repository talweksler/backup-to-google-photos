"""Configuration constants for Google Photos Backup Tool"""

import os

# OAuth 2.0 Configuration
SCOPES = [
    'https://www.googleapis.com/auth/photoslibrary.appendonly',  # Upload media and create albums
    'https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata'  # List and edit albums created by this app
]
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# API Configuration
API_SERVICE_NAME = 'photoslibrary'
API_VERSION = 'v1'
DISCOVERY_SERVICE_URL = 'https://photoslibrary.googleapis.com/$discovery/rest'

# Quota Management
DEFAULT_MAX_REQUESTS_PER_SESSION = 9500
DEFAULT_MAX_DAILY_REQUESTS = 10000
REQUEST_SAFETY_BUFFER = 500

# File Size Limits (in bytes)
MAX_PHOTO_SIZE = 200 * 1024 * 1024  # 200MB
MAX_VIDEO_SIZE = 10 * 1024 * 1024 * 1024  # 10GB

# Supported File Formats
SUPPORTED_IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
    '.heic', '.heif', '.webp'
}

SUPPORTED_VIDEO_FORMATS = {
    '.mp4', '.mov', '.avi', '.mkv', '.m4v', 
    '.webm', '.3gp'
}

SUPPORTED_FORMATS = SUPPORTED_IMAGE_FORMATS | SUPPORTED_VIDEO_FORMATS

# Upload Configuration
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks for large files
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
BACKOFF_FACTOR = 2

# State Management
STATE_DIR = '.backup_states'
STATE_FILE_PREFIX = 'state_'
STATE_FILE_SUFFIX = '.json'
STATE_VERSION = '1.0'

# Logging Configuration
LOG_DIR = 'logs'
LOG_DATE_FORMAT = '%Y-%m-%d'
LOG_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S %Z'  # Include timezone info
LOG_DATE_PACIFIC_FORMAT = '%Y-%m-%d'  # For Pacific date-based log filenames

# Album Configuration
MAX_ALBUM_NAME_LENGTH = 500
ALBUM_NAME_INVALID_CHARS = '<>:"/\\|?*'

def get_state_filename(directory_path: str) -> str:
    """
    Convert a directory path to a state filename.
    Example: '/Users/photos/vacation' -> 'state_users-photos-vacation.json'
    """
    # Normalize path and remove leading/trailing separators
    normalized_path = os.path.normpath(directory_path).strip(os.sep)
    
    # Replace path separators and invalid filename characters with hyphens
    sanitized = normalized_path.replace(os.sep, '-').replace('/', '-').replace('\\', '-')
    
    # Remove other potentially problematic characters
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '-')
    
    # Remove multiple consecutive hyphens
    while '--' in sanitized:
        sanitized = sanitized.replace('--', '-')
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Convert to lowercase for consistency
    sanitized = sanitized.lower()
    
    return f"{STATE_FILE_PREFIX}{sanitized}{STATE_FILE_SUFFIX}"

def get_state_filepath(directory_path: str) -> str:
    """Get the full path to the state file for a directory."""
    filename = get_state_filename(directory_path)
    return os.path.join(STATE_DIR, filename)

def ensure_directories_exist():
    """Create necessary directories if they don't exist."""
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

def is_supported_file(filename: str) -> bool:
    """Check if a file is a supported media format."""
    extension = os.path.splitext(filename)[1].lower()
    return extension in SUPPORTED_FORMATS

def is_image_file(filename: str) -> bool:
    """Check if a file is a supported image format."""
    extension = os.path.splitext(filename)[1].lower()
    return extension in SUPPORTED_IMAGE_FORMATS

def is_video_file(filename: str) -> bool:
    """Check if a file is a supported video format."""
    extension = os.path.splitext(filename)[1].lower()
    return extension in SUPPORTED_VIDEO_FORMATS

def get_max_file_size(filename: str) -> int:
    """Get the maximum allowed file size for a media type."""
    if is_image_file(filename):
        return MAX_PHOTO_SIZE
    elif is_video_file(filename):
        return MAX_VIDEO_SIZE
    else:
        return 0  # Unsupported file type

def sanitize_album_name(name: str) -> str:
    """Sanitize album name according to Google Photos requirements."""
    # Replace invalid characters with spaces
    sanitized = name
    for char in ALBUM_NAME_INVALID_CHARS:
        sanitized = sanitized.replace(char, ' ')
    
    # Remove extra whitespace
    sanitized = ' '.join(sanitized.split())
    
    # Truncate if too long
    if len(sanitized) > MAX_ALBUM_NAME_LENGTH:
        sanitized = sanitized[:MAX_ALBUM_NAME_LENGTH].strip()
    
    return sanitized