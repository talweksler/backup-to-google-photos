"""
Safe logging utility for Windows Unicode compatibility
"""
import logging
from datetime import datetime

def safe_log(level, message, include_time=False):
    """
    Unicode-safe logging wrapper that handles encoding errors
    
    Args:
        level: logging level (e.g., 'info', 'error', 'warning')
        message: message to log
        include_time: if True, prepend Pacific time to message
    """
    # Always create ASCII-safe version first
    safe_message = message
    
    # Add Pacific time prefix if requested
    if include_time:
        try:
            # Try to import timezone_utils, fallback to system time if not available
            try:
                from timezone_utils import format_pacific_time_for_logging
                time_str = format_pacific_time_for_logging()
            except ImportError:
                # Fallback to local system time
                time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            safe_message = f"[{time_str}] {safe_message}"
        except Exception:
            # If time formatting fails, just use the original message
            pass
    
    # Replace emojis with ASCII equivalents
    emoji_replacements = {
        '🚀': '[START]',
        '📁': '[FOLDER]',
        '📊': '[STATS]',
        '✅': '[OK]',
        '❌': '[ERROR]',
        '⚠️': '[WARNING]',
        '🔄': '[REFRESH]',
        '📋': '[LIST]',
        '💾': '[SAVE]',
        '🛑': '[STOP]',
        '🔐': '[AUTH]',
        '📚': '[BOOKS]',
        '🎯': '[TARGET]',
        '✨': '[NEW]',
        '📝': '[RESUME]',
        '🎉': '[SUCCESS]',
        '→': '->'
    }
    
    for emoji, replacement in emoji_replacements.items():
        safe_message = safe_message.replace(emoji, replacement)
    
    # Handle any remaining non-ASCII characters (like Hebrew)
    try:
        safe_message.encode('ascii')
    except UnicodeEncodeError:
        # If still has non-ASCII, encode with replacement
        safe_message = safe_message.encode('ascii', errors='replace').decode('ascii')
    
    # Log the safe version
    getattr(logging, level)(safe_message)