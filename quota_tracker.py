"""Quota tracking and management for Google Photos API"""

import logging
from typing import Optional
from datetime import datetime, timezone
from enum import Enum

from config import (
    DEFAULT_MAX_REQUESTS_PER_SESSION, 
    DEFAULT_MAX_DAILY_REQUESTS,
    REQUEST_SAFETY_BUFFER
)
from state_manager import BackupState

logger = logging.getLogger(__name__)

class QuotaLimitType(Enum):
    """Types of quota limits"""
    DAILY_LIMIT = "daily_limit"
    SESSION_LIMIT = "session_limit"
    NONE = "none"

class QuotaTracker:
    """Tracks and manages API quota usage"""
    
    def __init__(self, state: BackupState, max_session_requests: Optional[int] = None, 
                 max_daily_requests: Optional[int] = None):
        self.state = state
        self.max_session_requests = max_session_requests or DEFAULT_MAX_REQUESTS_PER_SESSION
        self.max_daily_requests = max_daily_requests or DEFAULT_MAX_DAILY_REQUESTS
        
    def record_requests(self, count: int = 1) -> bool:
        """
        Record API requests made.
        Returns True if we can continue, False if quota limit reached.
        """
        self.state.add_api_request(count)
        
        # Check if we've hit any limits
        limit_type = self.check_quota_limits()
        
        if limit_type != QuotaLimitType.NONE:
            reason = self._get_stop_reason(limit_type)
            self.state.set_stop_reason(reason)
            logger.warning(f"Quota limit reached: {reason}")
            return False
        
        return True
    
    def check_quota_limits(self) -> QuotaLimitType:
        """Check if any quota limits have been reached"""
        daily_usage = self.state.get_daily_quota_usage()
        session_usage = self.state.get_session_request_count()
        
        # Check daily limit
        if daily_usage >= self.max_daily_requests:
            return QuotaLimitType.DAILY_LIMIT
        
        # Check session limit
        if session_usage >= self.max_session_requests:
            return QuotaLimitType.SESSION_LIMIT
        
        return QuotaLimitType.NONE
    
    def can_make_requests(self, request_count: int = 1) -> bool:
        """Check if we can make the specified number of requests without hitting limits"""
        daily_usage = self.state.get_daily_quota_usage()
        session_usage = self.state.get_session_request_count()
        
        # Check against limits
        if daily_usage + request_count > self.max_daily_requests:
            return False
        
        if session_usage + request_count > self.max_session_requests:
            return False
        
        return True
    
    def get_remaining_daily_quota(self) -> int:
        """Get remaining daily quota"""
        daily_usage = self.state.get_daily_quota_usage()
        return max(0, self.max_daily_requests - daily_usage)
    
    def get_remaining_session_quota(self) -> int:
        """Get remaining session quota"""
        session_usage = self.state.get_session_request_count()
        return max(0, self.max_session_requests - session_usage)
    
    def get_remaining_quota(self) -> int:
        """Get the minimum remaining quota (most restrictive)"""
        return min(self.get_remaining_daily_quota(), self.get_remaining_session_quota())
    
    def get_quota_status(self) -> dict:
        """Get detailed quota status"""
        daily_usage = self.state.get_daily_quota_usage()
        session_usage = self.state.get_session_request_count()
        
        return {
            'daily': {
                'used': daily_usage,
                'limit': self.max_daily_requests,
                'remaining': self.get_remaining_daily_quota(),
                'percentage': round((daily_usage / self.max_daily_requests) * 100, 1)
            },
            'session': {
                'used': session_usage,
                'limit': self.max_session_requests,
                'remaining': self.get_remaining_session_quota(),
                'percentage': round((session_usage / self.max_session_requests) * 100, 1)
            },
            'can_continue': self.check_quota_limits() == QuotaLimitType.NONE
        }
    
    def _get_stop_reason(self, limit_type: QuotaLimitType) -> str:
        """Get human-readable stop reason for quota limit"""
        daily_usage = self.state.get_daily_quota_usage()
        session_usage = self.state.get_session_request_count()
        
        if limit_type == QuotaLimitType.DAILY_LIMIT:
            return f"Daily API quota reached ({daily_usage}/{self.max_daily_requests} requests). Resume tomorrow."
        elif limit_type == QuotaLimitType.SESSION_LIMIT:
            return f"Session limit reached ({session_usage}/{self.max_session_requests} requests). Resume with same command."
        else:
            return "Unknown quota limit reached"
    
    def estimate_requests_for_operation(self, operation_type: str, **kwargs) -> int:
        """Estimate number of API requests needed for an operation"""
        if operation_type == "upload_file":
            # Upload requires: upload bytes + create media item
            return 2
        elif operation_type == "create_album":
            # Creating an album requires 1 request
            return 1
        elif operation_type == "list_albums":
            # Listing albums - depends on number of albums
            # Default page size is 50, so 1 request per 50 albums
            total_albums = kwargs.get('estimated_albums', 50)
            return max(1, (total_albums + 49) // 50)  # Ceiling division
        elif operation_type == "add_to_album":
            # Adding media to album requires 1 request
            return 1
        else:
            # Conservative estimate for unknown operations
            return 1
    
    def can_perform_operation(self, operation_type: str, **kwargs) -> tuple[bool, str]:
        """
        Check if we can perform an operation without hitting quota limits.
        Returns (can_perform, reason_if_not)
        """
        estimated_requests = self.estimate_requests_for_operation(operation_type, **kwargs)
        
        if not self.can_make_requests(estimated_requests):
            limit_type = self.check_quota_limits()
            if limit_type != QuotaLimitType.NONE:
                return False, self._get_stop_reason(limit_type)
            
            # We're close to hitting a limit
            daily_remaining = self.get_remaining_daily_quota()
            session_remaining = self.get_remaining_session_quota()
            
            if daily_remaining < estimated_requests:
                return False, f"Not enough daily quota remaining ({daily_remaining} < {estimated_requests})"
            elif session_remaining < estimated_requests:
                return False, f"Not enough session quota remaining ({session_remaining} < {estimated_requests})"
        
        return True, ""
    
    def get_quota_summary(self) -> str:
        """Get human-readable quota summary"""
        status = self.get_quota_status()
        
        lines = [
            f"📊 Quota Status:",
            f"   Daily: {status['daily']['used']:,}/{status['daily']['limit']:,} ({status['daily']['percentage']}%)",
            f"   Session: {status['session']['used']:,}/{status['session']['limit']:,} ({status['session']['percentage']}%)",
            f"   Remaining: {self.get_remaining_quota():,} requests"
        ]
        
        # Add warning if getting close to limits
        if status['daily']['percentage'] > 80:
            lines.append("   ⚠️  Warning: Approaching daily limit")
        if status['session']['percentage'] > 80:
            lines.append("   ⚠️  Warning: Approaching session limit")
        
        return "\n".join(lines)
    
    def should_warn_about_quota(self) -> tuple[bool, str]:
        """Check if we should warn the user about quota usage"""
        status = self.get_quota_status()
        
        # Warn at 80% usage
        if status['daily']['percentage'] > 80:
            return True, f"Daily quota at {status['daily']['percentage']}% ({status['daily']['used']:,}/{status['daily']['limit']:,})"
        
        if status['session']['percentage'] > 80:
            return True, f"Session quota at {status['session']['percentage']}% ({status['session']['used']:,}/{status['session']['limit']:,})"
        
        return False, ""

def estimate_total_requests_for_backup(num_files: int, num_directories: int, 
                                     existing_albums: int = 0) -> int:
    """
    Estimate total API requests needed for a backup operation.
    
    Args:
        num_files: Number of files to upload
        num_directories: Number of directories (potential new albums)
        existing_albums: Number of existing albums to check
    
    Returns:
        Estimated total API requests
    """
    requests = 0
    
    # File uploads: 2 requests per file (upload + create media item)
    requests += num_files * 2
    
    # Album creation: 1 request per new album (worst case)
    requests += num_directories
    
    # Adding files to albums: 1 request per album (batch operation)
    requests += num_directories
    
    # Initial album listing to check existing albums
    requests += max(1, (existing_albums + 49) // 50)
    
    # Add 10% buffer for retries and edge cases
    requests = int(requests * 1.1)
    
    return requests

if __name__ == "__main__":
    # Test quota tracking
    logging.basicConfig(level=logging.INFO)
    
    from state_manager import BackupState
    
    test_dir = "/tmp/test_quota"
    print(f"Testing quota tracking for directory: {test_dir}")
    
    state = BackupState(test_dir)
    state.start_new_session()
    
    quota = QuotaTracker(state, max_session_requests=100, max_daily_requests=1000)
    
    print("Initial quota status:")
    print(quota.get_quota_summary())
    
    # Simulate some API usage
    print("\nSimulating API requests...")
    for i in range(5):
        if quota.record_requests(10):
            print(f"Recorded 10 requests (iteration {i+1})")
        else:
            print(f"Quota limit reached at iteration {i+1}")
            break
    
    print("\nFinal quota status:")
    print(quota.get_quota_summary())
    
    # Test operation checking
    can_upload, reason = quota.can_perform_operation("upload_file")
    print(f"\nCan upload file: {can_upload}")
    if not can_upload:
        print(f"Reason: {reason}")
    
    state.save_state()