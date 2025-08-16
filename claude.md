# Google Photos Backup Tool - Project Context

## Project Purpose
This is a Python script that uploads photos and videos from a local directory structure to Google Photos, preserving the folder hierarchy as albums. It's designed to handle large collections over multiple days while respecting API quotas.

## Key Technical Details

### Google Photos API Constraints
- **Daily Quota**: 10,000 API requests per day
- **File Size Limits**: 
  - Photos: 200MB max
  - Videos: 10GB max
- **Album Limits**: 20,000 items per album
- **Upload Process**: 2-step (upload bytes → create media item)
- **URL Expiration**: Upload URLs expire after 60 minutes
- **Scopes Required**: 
  - `photoslibrary.appendonly` - Upload media and create albums
  - `photoslibrary.edit.appcreateddata` - List/edit albums created by this app
- **Major Limitation**: Can ONLY access albums created by this app (not pre-existing albums)

### Supported Media Formats
**Images**: jpg, jpeg, png, gif, bmp, heic, heif, webp
**Videos**: mp4, mov, avi, mkv, m4v, webm, 3gp

### State Management System
- Each base directory gets its own state file
- State files stored in `.backup_states/` directory
- Filename format: `state_[sanitized-path].json`
- Tracks: uploaded files, API requests, failed uploads, created albums

### API Request Counting
- Each media upload = 2 requests minimum (upload + create)
- Album creation = 1 request
- Album listing = 1 request per 50 albums
- Safety stop at 9,500 requests (500 buffer)

## Development Guidelines

### Error Handling Philosophy
- **Fail gracefully**: Always save state before exiting
- **Clear communication**: Tell user exactly why script stopped
- **Resumable**: Design everything to be safely resumable
- **Retry logic**: 3 attempts for network failures

### Progress Reporting
- Show current directory being processed
- Display file being uploaded with size
- Track API request count in real-time
- Clear stop messages with actionable next steps

### Testing Priorities
1. State persistence across interruptions
2. Quota handling near limits
3. Large video uploads (5-10GB files)
4. Existing album detection
5. Network failure recovery

## Common Commands

### First Run
```bash
python main.py /path/to/photos
```

### Resume After Quota Limit
```bash
python main.py /path/to/photos  # Automatically resumes from state
```

### Skip Existing Albums
```bash
python main.py /path/to/photos --skip-existing
```

### Merge with Existing Albums
```bash
python main.py /path/to/photos --merge-existing
```

### Reset and Start Fresh
```bash
python main.py /path/to/photos --reset-state
```

## Architecture Decisions

### Why Per-Directory State Files?
- Users may backup multiple directories
- Each directory backup is independent
- Prevents state collision between different backup jobs
- Allows parallel backups of different directories

### Why Stop at 9,500 Requests?
- 500 request buffer for safety
- Accounts for potential API calls during shutdown
- Prevents accidental quota exhaustion
- Leaves room for other applications using same API key

### Why Not Use Service Accounts?
- Google Photos API doesn't support service accounts
- Must use OAuth 2.0 with user consent
- Each upload is tied to a specific user's library

## Known Limitations (Post-API Changes)
1. **Cannot see or access ANY albums created outside this app**
2. Cannot detect if an album name already exists (if created by user/other apps)
3. The `--skip-existing` and `--merge-existing` flags only work for albums created by THIS app
4. No way to detect true duplicates (must track by filename)
5. Base upload URLs expire quickly (60 min) - must use immediately

## Future Enhancements (Post-MVP)
- Parallel uploads for small files
- Checksum-based duplicate detection
- Export state to CSV for reporting
- Web UI for monitoring progress
- Automatic daily scheduling via cron/Task Scheduler
- Compression for large videos before upload

## Debugging Tips
- Check `.backup_states/` for state files
- Enable `--verbose` for detailed logging
- API errors usually have clear messages
- 403 errors = permission issues (check scope)
- 429 errors = rate limiting (add delays)
- 413 errors = file too large

## Important Files
- `token.json` - OAuth token (auto-refreshed)
- `credentials.json` - OAuth client credentials
- `.backup_states/state_*.json` - Progress tracking
- `logs/upload_[date].log` - Detailed logs per run