# Google Photos Backup Tool

A Python script that recursively uploads photos and videos from a local directory structure to Google Photos, preserving the folder hierarchy as albums. Designed to handle large collections over multiple days while respecting API quotas.

## 🌟 Features

- **📁 Recursive Upload**: Processes all subdirectories automatically
- **🎯 Smart Album Creation**: Each directory becomes a Google Photos album
- **💾 Resume Support**: Continues where it left off if interrupted
- **📊 Quota Management**: Respects API limits with clear progress reporting
- **🔄 Multiple Run Support**: Run daily until complete
- **📱 Multi-format Support**: Handles photos (JPEG, PNG, HEIC, etc.) and videos (MP4, MOV, etc.)
- **🛡️ Error Handling**: Robust error handling with retry logic
- **📈 Progress Tracking**: Real-time progress with detailed logging

## ⚠️ Important Limitations (Google API Changes)

Due to Google Photos API restrictions:
- **This app can ONLY see and manage albums it creates**
- **Cannot detect if an album name already exists in your library**
- **If an album with the same name exists, a duplicate will be created** (Google Photos allows multiple albums with identical names)
- The `--skip-existing` and `--merge-existing` flags only work for albums created by THIS app

**Example:** If you already have an album called "Vacation 2023" and run this tool on a folder named "Vacation 2023", it will create a NEW album also called "Vacation 2023". Both albums will exist separately in your library.

**💡 Tips to Avoid Duplicates:**
- Use the default naming (relative path) for a good balance of uniqueness and readability
- Use `--album-name-full` for maximum uniqueness when you have many similar folder names
- Avoid `--album-name-leaf` if you have common folder names like "photos", "images", etc.

## 🚀 Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Google Photos API**
   - Follow the detailed instructions in [`setup_credentials.md`](setup_credentials.md)
   - Download `credentials.json` to this directory

3. **Run Your First Backup**
   ```bash
   python main.py /path/to/your/photos
   ```

## 📖 Usage

### Basic Usage
```bash
python main.py /path/to/photos
```

### Handle Existing Albums (App-Created Only)
```bash
# Skip directories that already have albums created by THIS app
python main.py /path/to/photos --skip-existing

# Merge with existing albums created by THIS app (add new photos)
python main.py /path/to/photos --merge-existing
```

**Note:** These flags ONLY work for albums created by this app. They cannot detect or interact with albums created manually or by other apps.

### Album Naming Strategies

**Single Album for All Files:**
```bash
# Upload ALL files to one custom-named album
python main.py pics --album-name "Wedding Photos"
# Result: One album "Wedding Photos" containing all files from all subdirectories
```

**Directory-Based Albums (when --album-name is NOT used):**

For directory structure: `pics/south-america/brazil/`

```bash
# DEFAULT: Relative path (excludes base directory, concise but unique)
# Result: Album named "south-america-brazil"
python main.py pics

# Full path (includes base directory name)
# Result: Album named "pics-south-america-brazil"
python main.py pics --album-name-full

# Leaf only (just the last directory)
# Result: Album named "brazil"
python main.py pics --album-name-leaf
```

**Notes:** 
- `--album-name` uploads ALL files to a single album regardless of subdirectory structure
- The other naming strategies are mutually exclusive and only apply when `--album-name` is NOT used

### Control Options

**Preview Before Upload (Dry Run):**
```bash
# See what would be uploaded without actually uploading
python main.py /path/to/photos --dry-run
```

**Example Dry Run Output (Directory-Based Albums):**
```
📊 BACKUP SUMMARY
============================================================

📋 Albums That Would Be Created:
   📁 'europe-france' → 125 files
   📁 'south-america-argentina' → 89 files  
   📁 'south-america-brazil' → 234 files

📊 Album Summary:
   Total albums: 3
   Total files: 448
```

**Example with Custom Album Name:**
```bash
python main.py /path/to/photos --album-name "My Trip" --dry-run
```
```
📋 Albums That Would Be Created:
   📁 'My Trip' → 448 files

📊 Album Summary:
   Total albums: 1
   Total files: 448
```

**Other Options:**
```bash
# Verbose output for debugging
python main.py /path/to/photos --verbose

# Custom API request limit
python main.py /path/to/photos --max-requests 5000

# Start fresh (ignore previous progress)
python main.py /path/to/photos --reset-state
```

### State Management
```bash
# List all backup states
python main.py --list-states
```

## 🏗️ How It Works

### Directory Structure Example
```
pics/
├── south-america/
│   ├── brazil/
│   │   ├── rio.jpg
│   │   └── sao-paulo.jpg
│   └── argentina/
│       └── buenos-aires.jpg
└── europe/
    └── france/
        └── paris.jpg
```

### Album Names Created

**With `--album-name "My Trip"`:**
- One album: "My Trip" (contains ALL files from brazil/, argentina/, and france/)

**DEFAULT (relative path, no flags): `python main.py pics`**
- "south-america-brazil" 
- "south-america-argentina"
- "europe-france"

**With `--album-name-full`:**
- "pics-south-america-brazil"
- "pics-south-america-argentina"
- "pics-europe-france"

**With `--album-name-leaf`:**
- "brazil"
- "argentina"
- "france"

### Processing Order
The tool processes directories from deepest to shallowest (leaf directories first), so nested structures are handled properly.

## ⚡ API Quotas & Limits

- **Daily Quota**: 10,000 API requests per day
- **Session Limit**: 9,500 requests (with 500 safety buffer)
- **File Size Limits**: 
  - Photos: 200MB max
  - Videos: 10GB max
- **Album Limits**: 20,000 items per album

### Multi-Day Backups
For large collections:
1. Run the script daily
2. It automatically resumes where it left off
3. Clear stop messages tell you exactly why it stopped

### Stop Messages
- ✅ `"Completed: All files uploaded successfully"`
- ⚠️ `"Stopped: Daily API quota reached. Resume tomorrow."`
- 🛑 `"Stopped: User interruption. Progress saved."`
- ❌ `"Stopped: Network error after 3 retries."`

## 📁 Supported File Formats

### Images
- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- BMP (.bmp)
- WebP (.webp)
- HEIC/HEIF (.heic, .heif)

### Videos
- MP4 (.mp4)
- MOV (.mov)
- AVI (.avi)
- MKV (.mkv)
- M4V (.m4v)
- WebM (.webm)
- 3GP (.3gp)

## 🗂️ File Structure

```
backup-to-google-photos/
├── main.py                 # Main script
├── auth.py                 # Authentication logic
├── uploader.py            # Upload functionality
├── album_manager.py       # Album management
├── state_manager.py       # State persistence
├── quota_tracker.py       # API quota monitoring
├── config.py              # Configuration constants
├── requirements.txt       # Python dependencies
├── setup_credentials.md   # API setup instructions
├── README.md             # This file
├── credentials.json       # OAuth credentials (you create this)
├── token.json            # Stored auth token (auto-created)
├── .backup_states/       # State files per directory
└── logs/                 # Upload logs
```

## 🔒 Security & Privacy

- **OAuth 2.0**: Secure authentication with Google
- **Local Storage**: Credentials stored locally, never transmitted
- **Limited Permissions**: Uses only:
  - `photoslibrary.appendonly` - Upload media and create albums
  - `photoslibrary.edit.appcreateddata` - Manage albums created by this app
- **No Data Collection**: Tool doesn't collect or transmit your personal data
- **Isolated Access**: Can only see and modify content it creates

### Important Files to Keep Private
```gitignore
credentials.json  # Your OAuth client credentials
token.json       # Your access token
.backup_states/  # Progress tracking data
```

## 🛠️ Troubleshooting

### Common Issues

**"Authentication failed"**
- Check your `credentials.json` file
- Ensure Photos Library API is enabled
- Add your email as a test user in OAuth consent screen
- Make sure you have ONLY these scopes configured:
  - `photoslibrary.appendonly`
  - `photoslibrary.edit.appcreateddata`

**"Quota exceeded"** 
- Wait until next day (quota resets at midnight PT)
- Check usage in Google Cloud Console

**"File too large"**
- Photos: 200MB limit
- Videos: 10GB limit
- Tool automatically skips oversized files

**"Permission denied"**
- Check file/directory permissions
- Ensure you have read access to source directories

**"Duplicate albums created"**
- This is expected behavior due to API limitations
- The app cannot see albums created outside of it
- Consider organizing your photos differently before upload

### Debug Mode
```bash
python main.py /path/to/photos --verbose
```

### Check State
```bash
python main.py --list-states
```

### Fresh Start
```bash
python main.py /path/to/photos --reset-state
```

## 📊 Progress Tracking

Each backup creates a state file that tracks:
- ✅ Successfully uploaded files
- ❌ Failed uploads with error reasons
- 📊 API request counts
- 📁 Created albums
- 📍 Last processed directory

State files are named based on your source directory:
- `/Users/photos/vacation` → `state_users-photos-vacation.json`

## 🎯 Advanced Usage

### Estimate Backup Size
```bash
python main.py /path/to/photos --dry-run
```

### Multiple Backup Jobs
You can run backups for different directories independently:
```bash
python main.py /Users/photos/2023 --skip-existing &
python main.py /Users/photos/2024 --skip-existing &
```

Each gets its own state file, so they won't interfere.

### Monitoring Progress
- Check the logs in `logs/backup_YYYY-MM-DD.log`
- Use `--verbose` for detailed output
- State files contain complete progress information

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is open source. See LICENSE file for details.

## ⚠️ Disclaimer

This tool is not affiliated with Google. Use at your own risk. Always backup your original files independently.

## 🆘 Support

- 📚 Read [`setup_credentials.md`](setup_credentials.md) for API setup help
- 🐛 Check logs in `logs/` directory for error details  
- 💡 Use `--verbose` flag for debugging
- 📋 Use `--list-states` to check progress

For issues, please check existing logs and state files before reporting problems.