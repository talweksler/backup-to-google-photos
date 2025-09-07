"""
Safe logging utility for Windows Unicode compatibility
"""
import logging

def safe_log(level, message):
    """Unicode-safe logging wrapper that handles encoding errors"""
    # Always create ASCII-safe version first
    safe_message = message
    
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