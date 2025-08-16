# Google Photos Backup Tool - Development Plan

## Project Overview
A Python script that recursively uploads photos and videos from a local directory to Google Photos, creating albums for each subdirectory.

## Phase 1: Setup & Authentication (Day 1)
- [ ] Set up Python virtual environment
- [ ] Install required dependencies (google-api-python-client, google-auth-httplib2, google-auth-oauthlib)
- [ ] Create Google Cloud Project and enable Photos Library API
- [ ] Set up OAuth 2.0 credentials
- [ ] Implement authentication flow with photoslibrary.appendonly scope
- [ ] Test authentication and save credentials locally

## Phase 2: Core Upload Functionality (Day 2-3)
- [ ] Create main script structure with argument parsing
- [ ] Implement recursive directory traversal
- [ ] Create media upload function for both photos and videos
  - [ ] Handle upload bytes
  - [ ] Create media item from uploaded bytes
  - [ ] Support image formats: jpg, jpeg, png, gif, bmp, heic, heif, webp
  - [ ] Support video formats: mp4, mov, avi, mkv, m4v, webm, 3gp
- [ ] Implement rate limiting to avoid API throttling
- [ ] Add progress logging for each upload
- [ ] Handle upload errors with retry logic

## Phase 3: State Management & Progress Tracking (Day 3)
- [ ] Create state file system based on input directory
  - [ ] Generate state filename from directory path (e.g., `/Users/photos/vacation` → `state_users-photos-vacation.json`)
  - [ ] Store in `.backup_states/` directory
- [ ] Implement state tracking:
  - [ ] Last processed directory path
  - [ ] List of successfully uploaded files
  - [ ] API request count and timestamp
  - [ ] Current date's request count
  - [ ] Failed uploads with error reasons
- [ ] Add quota monitoring:
  - [ ] Track requests per session
  - [ ] Stop at 9,500 requests (safety margin)
  - [ ] Report clear stop reasons
- [ ] Implement resume functionality:
  - [ ] Check for existing state file on startup
  - [ ] Skip already uploaded files
  - [ ] Continue from last directory

## Phase 4: Album Management (Day 3-4)
- [ ] Implement album creation function
- [ ] Add album name validation and sanitization
- [ ] Check for existing albums before creation
- [ ] Implement --skip-existing flag functionality
- [ ] Implement --merge-existing flag functionality
- [ ] Link uploaded media to corresponding albums
- [ ] Handle album creation errors
- [ ] Track album IDs in state file

## Phase 5: Edge Cases & Error Handling (Day 4-5)
- [ ] Handle file size limitations:
  - [ ] Photos: 200MB max
  - [ ] Videos: 10GB max
- [ ] Skip unsupported file types with logging
- [ ] Implement duplicate detection based on filename
- [ ] Add comprehensive error logging with reasons
- [ ] Implement graceful shutdown on interruption
- [ ] Handle network timeouts for large video uploads
- [ ] Add file validation before upload attempt

## Phase 6: Testing & Documentation (Day 5-6)
- [ ] Create test directory structure with sample images and videos
- [ ] Test all flags and edge cases
- [ ] Test state persistence across multiple runs
- [ ] Write comprehensive README.md
- [ ] Add inline code documentation
- [ ] Create usage examples
- [ ] Test quota handling and resumption

## Technical Requirements

### Dependencies
- `google-api-python-client` - Google API client library
- `google-auth-httplib2` - HTTP/2 authentication
- `google-auth-oauthlib` - OAuth flow implementation
- `tqdm` - Progress bar display
- `python-magic` - File type detection (optional, for validation)

### File Structure
```
backup-to-google-photos/
├── main.py                 # Main script
├── auth.py                 # Authentication logic
├── uploader.py            # Upload functionality
├── album_manager.py       # Album management
├── state_manager.py       # State persistence and tracking
├── quota_tracker.py       # API quota monitoring
├── config.py              # Configuration constants
├── requirements.txt       # Python dependencies
├── credentials.json       # OAuth credentials (gitignored)
├── token.json            # Stored auth token (gitignored)
├── setup_credentials.md  # Instructions for API setup
├── README.md             # User documentation
├── .backup_states/       # State files directory (gitignored)
│   └── state_*.json      # Per-directory state files
└── logs/                 # Upload logs directory
```

### State File Structure
```json
{
  "base_directory": "/Users/photos/vacation",
  "state_version": "1.0",
  "created_at": "2024-01-15T10:00:00Z",
  "last_updated": "2024-01-15T14:30:00Z",
  "current_session": {
    "start_time": "2024-01-15T14:00:00Z",
    "api_requests_count": 4500,
    "last_processed_directory": "/Users/photos/vacation/day3",
    "stop_reason": null
  },
  "daily_quota": {
    "date": "2024-01-15",
    "total_requests": 4500
  },
  "uploaded_files": {
    "/Users/photos/vacation/day1/img1.jpg": {
      "uploaded_at": "2024-01-15T10:05:00Z",
      "media_item_id": "AGj1234...",
      "album_id": "APd5678..."
    }
  },
  "failed_uploads": {
    "/Users/photos/vacation/day2/corrupt.jpg": {
      "error": "Invalid image format",
      "attempts": 3,
      "last_attempt": "2024-01-15T11:00:00Z"
    }
  },
  "created_albums": {
    "day1": "APd5678...",
    "day2": "APd9012..."
  }
}
```

### Command Line Interface
```bash
python main.py <directory_path> [options]

Options:
  --skip-existing     Skip albums that already exist
  --merge-existing    Upload to existing albums with same name
  --dry-run          Show what would be uploaded without uploading
  --verbose          Detailed logging output
  --max-retries N    Maximum retry attempts for failed uploads (default: 3)
  --reset-state      Ignore existing state file and start fresh
  --max-requests N   Maximum API requests before stopping (default: 9500)
```

## API Considerations
- Google Photos API has a quota of 10,000 requests per day
- Upload is a 2-step process: upload bytes, then create media item
- Albums have a maximum of 20,000 items
- File size limits:
  - Photos: 200MB maximum
  - Videos: 10GB maximum
- Base URLs for uploaded bytes expire after 60 minutes
- OAuth tokens need periodic refresh
- Each upload = 2 API calls minimum (upload + create media item)
- Creating album = 1 API call
- Checking existing albums = 1 API call per page (50 albums/page)

## Stop Reasons & Status Messages
The script will clearly report why it stopped:
- ✅ "Completed: All files in [directory] uploaded successfully (X files, Y albums)"
- ⚠️ "Stopped: Daily API quota reached (9,500/10,000 requests). Resume tomorrow."
- ⚠️ "Stopped: Session limit reached (9,500 requests). Resume with same command."
- 🛑 "Stopped: User interruption at [directory]. Progress saved."
- ❌ "Stopped: Network error after 3 retries. Progress saved."
- ❌ "Stopped: Authentication failed. Please re-authenticate."

## Success Criteria
- Successfully uploads all images and videos from nested directories
- Creates appropriate album structure matching directory names
- Handles existing albums according to user preference
- Provides clear progress indication and stop reasons
- Persists state per base directory for reliable resumption
- Respects API quotas with clear reporting
- Supports daily runs with automatic progress continuation
- Handles large video uploads gracefully