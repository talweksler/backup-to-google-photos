"""
Timezone utilities for Google Photos Backup Tool

Handles Pacific Time (PT) for quota reset at 00:00 Pacific Time.
Google Photos API daily quota resets at midnight Pacific Time.
"""

import pytz
from datetime import datetime, timezone
from typing import Tuple


# Pacific timezone (handles PST/PDT automatically)
PACIFIC_TZ = pytz.timezone('US/Pacific')


def get_pacific_now() -> datetime:
    """Get current time in Pacific timezone"""
    return datetime.now(PACIFIC_TZ)


def get_utc_now() -> datetime:
    """Get current time in UTC timezone"""
    return datetime.now(timezone.utc)


def get_pacific_date_string(dt: datetime = None) -> str:
    """
    Get Pacific date as ISO string (YYYY-MM-DD)
    
    Args:
        dt: datetime object (if None, uses current time)
        
    Returns:
        Date string in Pacific timezone (e.g., '2025-09-08')
    """
    if dt is None:
        dt = get_pacific_now()
    elif dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Pacific time
    pacific_dt = dt.astimezone(PACIFIC_TZ)
    return pacific_dt.date().isoformat()


def get_pacific_datetime_string(dt: datetime = None) -> str:
    """
    Get Pacific datetime as ISO string with timezone info
    
    Args:
        dt: datetime object (if None, uses current time)
        
    Returns:
        Datetime string in Pacific timezone (e.g., '2025-09-08T15:30:45-07:00')
    """
    if dt is None:
        dt = get_pacific_now()
    elif dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Pacific time
    pacific_dt = dt.astimezone(PACIFIC_TZ)
    return pacific_dt.isoformat()


def format_pacific_time_for_logging(dt: datetime = None, include_timezone: bool = True) -> str:
    """
    Format datetime for logging in Pacific time
    
    Args:
        dt: datetime object (if None, uses current time)
        include_timezone: whether to include timezone abbreviation (PST/PDT)
        
    Returns:
        Formatted string for logging (e.g., '2025-09-08 15:30:45 PDT')
    """
    if dt is None:
        dt = get_pacific_now()
    elif dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Pacific time
    pacific_dt = dt.astimezone(PACIFIC_TZ)
    
    if include_timezone:
        # Format with timezone abbreviation (PST or PDT)
        return pacific_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    else:
        return pacific_dt.strftime('%Y-%m-%d %H:%M:%S')


def has_pacific_date_changed(stored_date: str) -> Tuple[bool, str]:
    """
    Check if the Pacific date has changed since the stored date
    
    Args:
        stored_date: Previously stored date string (YYYY-MM-DD)
        
    Returns:
        Tuple of (has_changed: bool, current_date: str)
    """
    current_date = get_pacific_date_string()
    has_changed = stored_date != current_date
    
    return has_changed, current_date


def convert_utc_to_pacific_string(utc_iso_string: str) -> str:
    """
    Convert UTC ISO string to Pacific time string for display
    
    Args:
        utc_iso_string: UTC datetime string (e.g., '2025-09-08T22:30:45.123456+00:00')
        
    Returns:
        Pacific time string for display (e.g., '2025-09-08 15:30:45 PDT')
    """
    try:
        # Parse UTC datetime
        utc_dt = datetime.fromisoformat(utc_iso_string.replace('Z', '+00:00'))
        
        # Convert to Pacific and format
        return format_pacific_time_for_logging(utc_dt)
    except (ValueError, TypeError):
        # Fallback to original string if parsing fails
        return utc_iso_string


def get_next_pacific_midnight() -> datetime:
    """
    Get the next midnight in Pacific time
    
    Returns:
        datetime object representing next midnight Pacific time
    """
    pacific_now = get_pacific_now()
    
    # Get tomorrow's date in Pacific time
    tomorrow = pacific_now.date().replace(day=pacific_now.day + 1)
    
    # Create midnight datetime in Pacific timezone
    midnight_pacific = PACIFIC_TZ.localize(
        datetime.combine(tomorrow, datetime.min.time())
    )
    
    return midnight_pacific


def seconds_until_pacific_midnight() -> int:
    """
    Get seconds until next midnight Pacific time
    
    Returns:
        Number of seconds until next Pacific midnight
    """
    now = get_pacific_now()
    next_midnight = get_next_pacific_midnight()
    
    return int((next_midnight - now).total_seconds())


if __name__ == "__main__":
    # Test the timezone utilities
    print("=== Timezone Utilities Test ===")
    
    print(f"Current Pacific time: {get_pacific_now()}")
    print(f"Current UTC time: {get_utc_now()}")
    
    print(f"Pacific date string: {get_pacific_date_string()}")
    print(f"Pacific datetime string: {get_pacific_datetime_string()}")
    
    print(f"Logging format: {format_pacific_time_for_logging()}")
    print(f"Logging format (no TZ): {format_pacific_time_for_logging(include_timezone=False)}")
    
    # Test date change detection
    yesterday = "2025-09-07"
    changed, current = has_pacific_date_changed(yesterday)
    print(f"Date changed from {yesterday}: {changed}, current: {current}")
    
    # Test UTC conversion
    utc_string = "2025-09-08T22:30:45+00:00"
    pacific_display = convert_utc_to_pacific_string(utc_string)
    print(f"UTC {utc_string} -> Pacific: {pacific_display}")
    
    # Test midnight calculation
    next_midnight = get_next_pacific_midnight()
    seconds_left = seconds_until_pacific_midnight()
    print(f"Next Pacific midnight: {next_midnight}")
    print(f"Seconds until midnight: {seconds_left}")