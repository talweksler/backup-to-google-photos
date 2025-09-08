#!/usr/bin/env python3
"""
Google Photos Backup Tool

A Python script that recursively uploads photos and videos from a local directory 
to Google Photos, creating albums for each subdirectory.
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import List, Tuple
import signal
from tqdm import tqdm

# Import our modules
from config import ensure_directories_exist, LOG_DIR, LOG_TIMESTAMP_FORMAT
from auth import GooglePhotosAuth
from state_manager import BackupState, list_all_states
from quota_tracker import QuotaTracker, estimate_total_requests_for_backup
from album_manager import AlbumManager, AlbumExistsAction
from uploader import MediaUploader, get_directory_media_count
from safe_logging import safe_log

# System directories and files to skip
SKIP_DIRECTORIES = {
    '.aux',     # Windows auxiliary files
    '.tmp',     # Temporary files
    '.temp',    # Temporary files
    '$recycle.bin',  # Windows recycle bin
    'system volume information',  # Windows system folder
    '.trashes', # macOS trash
    '.DS_Store', # macOS system files
    'thumbs.db', # Windows thumbnail cache
    '@eaDir',   # Synology NAS system folder
    '.@__thumb', # Synology thumbnails
    '.picasa',  # Google Picasa cache
    '.picasaoriginals' # Picasa backups
}

# Global variables for signal handling
interrupted = False
current_state = None

def should_skip_directory(directory_path: str) -> bool:
    """Check if a directory should be skipped based on system directory patterns"""
    dir_name = os.path.basename(directory_path).lower()
    
    # Check against skip list
    if dir_name in SKIP_DIRECTORIES:
        return True
    
    # Check for hidden directories (starting with .)
    if dir_name.startswith('.') and len(dir_name) > 1:
        return True
    
    # Check for Windows system attributes or patterns
    if dir_name.startswith('$') or dir_name.startswith('@'):
        return True
        
    return False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global interrupted, current_state
    print("\n[STOP] Interrupt signal received. Saving progress and stopping...")
    interrupted = True
    if current_state:
        current_state.set_stop_reason("User interruption (Ctrl+C)")
        current_state.save_state()
    print("[SAVE] Progress saved. Exiting...")
    sys.exit(0)

def setup_logging(verbose: bool = False, log_file: str = None):
    """Set up logging configuration"""
    ensure_directories_exist()
    
    # Create log filename if not provided
    if not log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"backup_{timestamp}.log")
    
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        f'%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt=LOG_TIMESTAMP_FORMAT
    )
    
    simple_formatter = logging.Formatter('%(message)s')
    
    # Set up root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # File handler (always detailed)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler (encoding handled at startup for Windows)
    console_handler = logging.StreamHandler()
    
    console_handler.setLevel(log_level)
    if verbose:
        console_handler.setFormatter(detailed_formatter)
    else:
        console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    return log_file

def get_all_subdirectories(base_path: str) -> List[str]:
    """Get all subdirectories recursively, sorted by depth (deepest first)"""
    subdirs = []
    skipped_count = 0
    
    try:
        for root, dirs, files in os.walk(base_path):
            # Skip system directories
            if should_skip_directory(root):
                skipped_count += 1
                continue
            
            # Filter out system directories from the dirs list to prevent os.walk from entering them
            dirs[:] = [d for d in dirs if not should_skip_directory(os.path.join(root, d))]
            
            # Only include directories that have media files
            total_files, supported_files = get_directory_media_count(root)
            if supported_files > 0:
                subdirs.append(root)
    
    except PermissionError as e:
        safe_log('error', f"Permission denied accessing {base_path}: {e}")
        return []
    
    except Exception as e:
        safe_log('error', f"Error walking directory {base_path}: {e}")
        return []
    
    # Sort by depth (deepest first) to process leaf directories first
    subdirs.sort(key=lambda x: x.count(os.sep), reverse=True)
    
    if skipped_count > 0:
        safe_log('info', f"Skipped {skipped_count} system/hidden directories")
    
    return subdirs

def estimate_backup_scope(base_directory: str) -> Tuple[int, int, int]:
    """
    Estimate the scope of a backup operation.
    Returns (total_files, total_directories, estimated_requests)
    """
    total_files = 0
    directories_with_media = 0
    
    for root, dirs, files in os.walk(base_directory):
        # Skip system directories
        if should_skip_directory(root):
            continue
            
        # Filter out system directories from the dirs list to prevent os.walk from entering them
        dirs[:] = [d for d in dirs if not should_skip_directory(os.path.join(root, d))]
        
        total_dir_files, supported_files = get_directory_media_count(root)
        if supported_files > 0:
            total_files += supported_files
            directories_with_media += 1
    
    estimated_requests = estimate_total_requests_for_backup(total_files, directories_with_media)
    
    return total_files, directories_with_media, estimated_requests

def process_directory(directory: str, album_manager: AlbumManager, uploader: MediaUploader, 
                     exists_action: str, dry_run: bool = False, 
                     base_directory: str = None, naming_strategy: str = "relative", 
                     custom_album_name: str = None, album_id: str = None) -> Tuple[bool, int, int, int, str]:
    """
    Process a single directory: create album and upload files.
    naming_strategy: "relative" (default), "full", or "leaf"
    Returns (success, uploaded_count, skipped_count, failed_count, album_name)
    """
    global interrupted
    
    if interrupted:
        return False, 0, 0, 0, ""
    
    # Determine album name and ID
    if custom_album_name:
        # Use the provided custom album name
        album_name = custom_album_name
        # If album_id is provided, use it (for single album uploads)
        if album_id:
            target_album_id = album_id
            created_new = False
        else:
            # Create/get the album (this should only happen once for custom names, skip for dry run)
            if not dry_run:
                target_album_id, created_new = album_manager.get_or_create_album(album_name, exists_action)
            else:
                target_album_id, created_new = None, False
    else:
        # Generate album name based on naming strategy
        if naming_strategy == "leaf":
            # Use only the leaf directory name
            album_name = os.path.basename(directory)
            if not album_name:
                album_name = "Root"
        elif naming_strategy == "full":
            # Use full path including base directory
            if base_directory:
                # Get the base directory name and combine with relative path
                base_name = os.path.basename(base_directory.rstrip(os.sep))
                rel_path = os.path.relpath(directory, base_directory)
                if rel_path == ".":
                    album_name = base_name if base_name else "Root"
                else:
                    # Combine base name with relative path
                    album_name = f"{base_name}-{rel_path.replace(os.sep, '-')}"
            else:
                album_name = os.path.basename(directory)
                if not album_name:
                    album_name = "Root"
        else:
            # Default: relative path excluding base directory
            if base_directory:
                rel_path = os.path.relpath(directory, base_directory)
                if rel_path == ".":
                    # If we're at the base directory itself, use its name
                    album_name = os.path.basename(base_directory) if os.path.basename(base_directory) else "Root"
                else:
                    # Use relative path with dashes
                    album_name = rel_path.replace(os.sep, "-")
            else:
                album_name = os.path.basename(directory)
                if not album_name:
                    album_name = "Root"
        
        # Create/get the album for directory-based naming (skip for dry run)
        if not dry_run:
            target_album_id, created_new = album_manager.get_or_create_album(album_name, exists_action)
        else:
            target_album_id, created_new = None, False
    
    safe_log('info', f"\n📁 Processing directory: {directory}")
    safe_log('info', f"   Album name: {album_name}")
    
    # Count files in directory
    total_files, supported_files = get_directory_media_count(directory)
    
    if supported_files == 0:
        logging.info(f"   No supported media files found, skipping")
        return True, 0, total_files, 0, ""
    
    logging.info(f"   Found {supported_files} supported files (of {total_files} total)")
    
    if dry_run:
        safe_log('info', f"   [DRY RUN] Would create album '{album_name}' and upload {supported_files} files")
        return True, 0, supported_files, 0, album_name
    
    if target_album_id is None:
        if exists_action == AlbumExistsAction.SKIP:
            safe_log('info', f"   Skipped existing album: {album_name}")
            return True, 0, supported_files, 0, album_name
        else:
            safe_log('error', f"   Failed to create/get album: {album_name}")
            return False, 0, 0, supported_files, album_name
    
    if custom_album_name and album_id:
        # For single album uploads, don't log creation since it was done earlier
        safe_log('info', f"   📁 Adding to album: {album_name} ({target_album_id})")
    elif created_new:
        safe_log('info', f"   ✨ Created new album: {album_name} ({target_album_id})")
    else:
        safe_log('info', f"   📁 Using existing album: {album_name} ({target_album_id})")
    
    # Upload files in directory
    uploaded, skipped, failed = uploader.upload_directory_files(directory, target_album_id)
    
    safe_log('info', f"   📊 Results: {uploaded} uploaded, {skipped} skipped, {failed} failed")
    
    return True, uploaded, skipped, failed, album_name

def run_backup(args):
    """Main backup function"""
    global interrupted, current_state
    
    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    base_directory = os.path.abspath(args.directory)
    
    # Validate directory
    if not os.path.exists(base_directory):
        safe_log('error', f"Directory does not exist: {base_directory}")
        return 1
    
    if not os.path.isdir(base_directory):
        safe_log('error', f"Path is not a directory: {base_directory}")
        return 1
    
    safe_log('info', f"🚀 Starting Google Photos backup")
    safe_log('info', f"   Source directory: {base_directory}")
    logging.info(f"   Dry run: {'Yes' if args.dry_run else 'No'}")
    
    # Initialize state
    state = BackupState(base_directory)
    current_state = state
    
    # Check if we should reset state
    if args.reset_state:
        safe_log('info', "🔄 Resetting state (fresh start)")
        state.delete_state_file()
        state = BackupState(base_directory)
        current_state = state
    elif args.reset_quota_only:
        safe_log('info', "🔄 Resetting quota counters to 0")
        # Reset daily and session quota counters while keeping upload progress
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        state.state_data['daily_quota'] = {
            'date': today,
            'total_requests': 0
        }
        state.state_data['current_session']['api_requests_count'] = 0
        state.save_state()
        safe_log('info', "✅ Quota counters reset to 0, upload progress preserved")
    elif args.set_quota_usage is not None:
        safe_log('info', f"🔄 Setting daily quota usage to {args.set_quota_usage}")
        # Set daily quota to match Google API console usage
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        state.state_data['daily_quota'] = {
            'date': today,
            'total_requests': args.set_quota_usage
        }
        state.state_data['current_session']['api_requests_count'] = 0
        state.save_state()
        safe_log('info', f"✅ Daily quota set to {args.set_quota_usage}, session reset to 0, upload progress preserved")
    
    # Show existing state info
    last_dir = state.get_last_processed_directory()
    if last_dir:
        safe_log('info', f"📝 Resuming from previous session")
        safe_log('info', f"   Last processed: {last_dir}")
        safe_log('info', f"   Files uploaded so far: {len(state.get_uploaded_files())}")
    
    state.start_new_session()
    
    # Estimate backup scope
    safe_log('info', "📊 Analyzing backup scope...")
    total_files, total_dirs, estimated_requests = estimate_backup_scope(base_directory)
    
    # Get already uploaded count
    already_uploaded = len(state.get_uploaded_files())
    remaining_files = max(0, total_files - already_uploaded)
    
    logging.info(f"   Total supported files: {total_files:,}")
    logging.info(f"   Already uploaded: {already_uploaded:,}")
    logging.info(f"   Remaining to upload: {remaining_files:,}")
    logging.info(f"   Directories with media: {total_dirs:,}")
    
    if not args.dry_run:
        logging.info(f"   Estimated API requests: {estimated_requests:,}")
        
        if estimated_requests > 9000:
            safe_log('warning', f"⚠️  Large backup detected! This may require multiple days to complete.")
    
    # Authenticate
    if not args.dry_run:
        safe_log('info', "🔐 Authenticating with Google Photos...")
        auth = GooglePhotosAuth()
        if not auth.authenticate():
            safe_log('error', "❌ Authentication failed")
            return 1
        
        service = auth.get_service()
        if not service:
            safe_log('error', "❌ Failed to initialize Google Photos service")
            return 1
        
        if not auth.test_connection():
            safe_log('error', "❌ API connection test failed")
            return 1
        
        safe_log('info', "✅ Authentication successful")
    else:
        service = None
    
    # Initialize components
    quota = QuotaTracker(state, max_session_requests=args.max_requests)
    
    # Debug: Show current quota status
    daily_usage = state.get_daily_quota_usage()
    session_usage = state.get_session_request_count()
    safe_log('info', f"[DEBUG] Quota status: Daily={daily_usage}/10000, Session={session_usage}/{args.max_requests}")
    
    if not args.dry_run:
        album_manager = AlbumManager(service, state, quota)
        uploader = MediaUploader(service, state, quota)
        
        # Set total files count for progress tracking
        uploader.set_total_files_count(total_files)
        
        # Load existing albums
        safe_log('info', "📚 Loading existing albums...")
        if not album_manager.load_existing_albums():
            safe_log('error', "❌ Failed to load existing albums")
            return 1
    else:
        album_manager = None
        uploader = None
    
    # Determine exists action
    if args.skip_existing:
        exists_action = AlbumExistsAction.SKIP
        safe_log('info', "📋 Policy: Skip existing albums")
    elif args.merge_existing:
        exists_action = AlbumExistsAction.MERGE
        safe_log('info', "📋 Policy: Merge with existing albums")
    else:
        exists_action = AlbumExistsAction.STOP
        safe_log('info', "📋 Policy: Stop if album exists")
    
    # Get directories to process
    directories = get_all_subdirectories(base_directory)
    
    if not directories:
        safe_log('warning', "⚠️  No directories with supported media files found")
        return 0
    
    safe_log('info', f"📁 Found {len(directories)} directories to process")
    
    # Handle custom album name (single album for all files)
    custom_album_id = None
    if args.album_name and not args.dry_run:
        # Create the single album once
        safe_log('info', f"🎯 Creating single album '{args.album_name}' for all files...")
        custom_album_id, created_new = album_manager.get_or_create_album(args.album_name, exists_action)
        if custom_album_id is None:
            if exists_action == AlbumExistsAction.SKIP:
                safe_log('info', f"   Skipped existing album: {args.album_name}")
                return 0
            else:
                safe_log('error', f"❌ Failed to create album: {args.album_name}")
                return 1
        
        if created_new:
            safe_log('info', f"   ✨ Created new album: {args.album_name} ({custom_album_id})")
        else:
            safe_log('info', f"   📁 Using existing album: {args.album_name} ({custom_album_id})")
    
    # Process directories
    total_uploaded = 0
    total_skipped = 0
    total_failed = 0
    album_preview = {}  # For dry run: {album_name: file_count}
    
    with tqdm(directories, desc="Processing directories", disable=args.verbose) as pbar:
        for directory in pbar:
            if interrupted:
                safe_log('info', "🛑 Processing interrupted by user")
                break
            
            pbar.set_description(f"Processing: {os.path.basename(directory)}")
            
            state.set_last_processed_directory(directory)
            
            # Determine naming strategy (only used if no custom album name)
            if args.album_name_full:
                naming_strategy = "full"
            elif args.album_name_leaf:
                naming_strategy = "leaf"
            else:
                naming_strategy = "relative"  # default
            
            success, uploaded, skipped, failed, album_name = process_directory(
                directory, album_manager, uploader, exists_action, args.dry_run,
                base_directory=base_directory, naming_strategy=naming_strategy,
                custom_album_name=args.album_name, album_id=custom_album_id
            )
            
            # Collect album names for dry run preview
            if args.dry_run and album_name:
                if album_name in album_preview:
                    album_preview[album_name] += skipped  # skipped = supported files in dry run
                else:
                    album_preview[album_name] = skipped
            
            total_uploaded += uploaded
            total_skipped += skipped
            total_failed += failed
            
            if not success:
                safe_log('error', f"❌ Failed to process directory: {directory}")
                if not args.dry_run:
                    state.set_stop_reason(f"Failed to process directory: {directory}")
                    break
            
            # Check quota limits
            if not args.dry_run and not quota.check_quota_limits():
                break
            
            # Save state after each directory
            state.save_state()
    
    # Final summary
    logging.info("\n" + "="*60)
    safe_log('info', "📊 BACKUP SUMMARY")
    logging.info("="*60)
    
    if not args.dry_run:
        safe_log('info', state.get_summary())
        safe_log('info', "\n" + quota.get_quota_summary())
        
        if album_manager:
            safe_log('info', "\n" + album_manager.get_albums_summary())
    
    # Show album preview for dry runs
    if args.dry_run and album_preview:
        safe_log('info', f"\n📋 Albums That Would Be Created:")
        total_albums = len(album_preview)
        total_files_in_albums = sum(album_preview.values())
        
        for album_name, file_count in sorted(album_preview.items()):
            safe_log('info', f"   📁 '{album_name}' → {file_count:,} files")
        
        safe_log('info', f"\n📊 Album Summary:")
        logging.info(f"   Total albums: {total_albums}")
        logging.info(f"   Total files: {total_files_in_albums:,}")
    
    safe_log('info', f"\n📁 Directory Processing:")
    logging.info(f"   Files uploaded: {total_uploaded:,}")
    logging.info(f"   Files skipped: {total_skipped:,}")
    logging.info(f"   Files failed: {total_failed:,}")
    
    # Check for completion
    if interrupted:
        safe_log('info', "\n🛑 Backup interrupted by user")
        return 0
    elif total_failed > 0:
        safe_log('info', f"\n⚠️  Backup completed with {total_failed} failures")
        return 1
    else:
        if args.dry_run:
            safe_log('info', "\n✅ Dry run completed successfully")
        else:
            safe_log('info', "\n🎉 Backup completed successfully!")
        return 0

def list_states_command(args):
    """List all existing state files"""
    states = list_all_states()
    
    if not states:
        print("No backup states found.")
        return 0
    
    print(f"Found {len(states)} backup state(s):\n")
    
    for state_file in states:
        try:
            # Extract directory from filename
            basename = os.path.basename(state_file)
            print(f"State file: {basename}")
            
            # Load and show summary
            with open(state_file, 'r') as f:
                import json
                data = json.load(f)
            
            base_dir = data.get('base_directory', 'Unknown')
            uploaded_count = len(data.get('uploaded_files', {}))
            failed_count = len(data.get('failed_uploads', {}))
            last_updated = data.get('last_updated', 'Unknown')
            
            print(f"  Directory: {base_dir}")
            print(f"  Files uploaded: {uploaded_count}")
            print(f"  Files failed: {failed_count}")
            print(f"  Last updated: {last_updated}")
            print()
            
        except Exception as e:
            print(f"  Error reading state: {e}")
            print()
    
    return 0

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Upload photos and videos to Google Photos with album organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
⚠️  IMPORTANT API LIMITATIONS:
  Due to Google Photos API restrictions, this app can ONLY see and manage albums it creates.
  • Cannot detect if an album name already exists in your library
  • Will create duplicate albums if the name matches existing albums
  • The --skip-existing and --merge-existing flags ONLY work for albums created by THIS app
  
  Example: If you already have an album "Vacation 2023" and run this tool on a folder 
  named "Vacation 2023", you'll end up with TWO albums both named "Vacation 2023".

Album Naming Options:
  --album-name "My Album"      → All files go to "My Album" (single album)
  
  When --album-name is NOT used, directory-based naming applies:
  Given directory structure: pics/south-america/brazil/
  
  DEFAULT (relative path):     → "south-america-brazil"
  --album-name-full (full):    → "pics-south-america-brazil"  
  --album-name-leaf (leaf):    → "brazil"

Examples:
  python main.py /path/to/photos --album-name "Wedding Photos"  # Single album
  python main.py /path/to/photos                               # Default naming  
  python main.py /path/to/photos --album-name-full             # Include base directory
  python main.py /path/to/photos --album-name-leaf             # Leaf directory only
  python main.py --list-states
        """
    )
    
    parser.add_argument('directory', nargs='?',
                       help='Directory to backup (required unless using --list-states)')
    
    # Album handling options
    parser.add_argument('--skip-existing', action='store_true',
                       help='Skip albums that already exist (NOTE: Only detects albums created by THIS app, not pre-existing albums)')
    parser.add_argument('--merge-existing', action='store_true',
                       help='Upload to existing albums with same name (NOTE: Only works with albums created by THIS app)')
    
    # Album naming options
    parser.add_argument('--album-name', type=str,
                       help='Use a custom album name for all files (uploads all files to a single album regardless of directory structure)')
    
    # Album naming strategy (mutually exclusive group) - only used if --album-name not specified
    naming_group = parser.add_mutually_exclusive_group()
    naming_group.add_argument('--album-name-full', action='store_true',
                       help='Include base directory in album name: pics/south-america/brazil → "pics-south-america-brazil"')
    naming_group.add_argument('--album-name-leaf', action='store_true',
                       help='Use only the leaf directory name: pics/south-america/brazil → "brazil"')
    
    # Control options
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be uploaded without uploading')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging output')
    parser.add_argument('--max-requests', type=int, default=9500,
                       help='Maximum API requests before stopping (default: 9500)')
    
    # State management
    parser.add_argument('--reset-state', action='store_true',
                       help='Ignore existing state file and start fresh')
    parser.add_argument('--reset-quota-only', action='store_true',
                       help='Reset only quota counters to 0, keep upload progress')
    parser.add_argument('--set-quota-usage', type=int, metavar='COUNT',
                       help='Set daily quota usage to specific number (from Google API console)')
    parser.add_argument('--list-states', action='store_true',
                       help='List all existing backup states and exit')
    
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    # Handle list-states command
    if args.list_states:
        return list_states_command(args)
    
    # Validate required arguments
    if not args.directory:
        parser.error("directory argument is required unless using --list-states")
    
    # Validate conflicting options
    if args.skip_existing and args.merge_existing:
        parser.error("--skip-existing and --merge-existing cannot be used together")
    
    # Set up logging
    log_file = setup_logging(args.verbose)
    safe_log('info', f"Logging to: {log_file}")
    
    try:
        return run_backup(args)
    except KeyboardInterrupt:
        safe_log('info', "\n🛑 Backup interrupted")
        return 0
    except Exception as e:
        safe_log('error', f"❌ Unexpected error: {e}")
        import traceback
        logging.debug(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())