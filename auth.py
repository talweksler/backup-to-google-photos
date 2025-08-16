"""Authentication module for Google Photos API"""

import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
from typing import Optional

from config import (
    SCOPES, CREDENTIALS_FILE, TOKEN_FILE, API_SERVICE_NAME, 
    API_VERSION, DISCOVERY_SERVICE_URL
)

logger = logging.getLogger(__name__)

class GooglePhotosAuth:
    """Handle Google Photos API authentication"""
    
    def __init__(self):
        self.credentials: Optional[Credentials] = None
        self.service = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with Google Photos API.
        Returns True if authentication successful, False otherwise.
        """
        try:
            # Load existing credentials
            if os.path.exists(TOKEN_FILE):
                logger.info("Loading existing credentials...")
                self.credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            
            # If there are no valid credentials available, request authorization
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    logger.info("Refreshing expired credentials...")
                    try:
                        self.credentials.refresh(Request())
                    except Exception as e:
                        logger.warning(f"Failed to refresh credentials: {e}")
                        self.credentials = None
                
                # If refresh failed or no credentials, get new ones
                if not self.credentials:
                    logger.info("Requesting new credentials...")
                    if not os.path.exists(CREDENTIALS_FILE):
                        logger.error(f"Credentials file not found: {CREDENTIALS_FILE}")
                        logger.error("Please follow setup_credentials.md to create this file.")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        CREDENTIALS_FILE, SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
            
            # Save the credentials for next time
            with open(TOKEN_FILE, 'w') as token:
                token.write(self.credentials.to_json())
            
            logger.info("Authentication successful!")
            return True
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def build_service(self):
        """Build and return the Google Photos API service object"""
        if not self.credentials:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        try:
            self.service = build(
                API_SERVICE_NAME, 
                API_VERSION, 
                credentials=self.credentials,
                discoveryServiceUrl=DISCOVERY_SERVICE_URL,
                cache_discovery=False
            )
            logger.info("Google Photos API service initialized")
            return self.service
            
        except Exception as e:
            logger.error(f"Failed to build service: {e}")
            raise
    
    def get_service(self):
        """Get the authenticated service object"""
        if not self.service:
            if not self.credentials:
                if not self.authenticate():
                    raise Exception("Authentication failed")
            self.build_service()
        
        return self.service
    
    def test_connection(self) -> bool:
        """Test the API connection by verifying the service is properly initialized"""
        try:
            service = self.get_service()
            # With the new API constraints, we can only list albums created by this app
            # On first run, there may be no albums yet, so we just verify the service exists
            if service:
                logger.info("API connection test successful - service initialized")
                # Try to list albums created by this app (may be empty)
                try:
                    result = service.albums().list(pageSize=1).execute()
                    logger.info(f"Can access albums API (found {result.get('albums', []).__len__()} app-created albums)")
                except HttpError as e:
                    # 403 is expected if no albums created yet by this app
                    if e.resp.status == 403:
                        logger.info("No app-created albums found yet (normal for first run)")
                    else:
                        raise e
                return True
            return False
            
        except HttpError as e:
            logger.error(f"API connection test failed: {e}")
            if e.resp.status == 401:
                logger.error("Authentication failed. Try deleting token.json and re-authenticating.")
            return False
            
        except Exception as e:
            logger.error(f"API connection test failed with unexpected error: {e}")
            return False
    
    def revoke_credentials(self):
        """Revoke and delete stored credentials"""
        try:
            if self.credentials:
                # Revoke the credentials
                revoke_url = f'https://oauth2.googleapis.com/revoke?token={self.credentials.token}'
                import requests
                response = requests.post(revoke_url)
                if response.status_code == 200:
                    logger.info("Credentials revoked successfully")
                else:
                    logger.warning(f"Failed to revoke credentials: {response.status_code}")
            
            # Delete local files
            for file in [TOKEN_FILE, CREDENTIALS_FILE]:
                if os.path.exists(file):
                    os.remove(file)
                    logger.info(f"Deleted {file}")
            
            self.credentials = None
            self.service = None
            
        except Exception as e:
            logger.error(f"Failed to revoke credentials: {e}")

def get_authenticated_service():
    """
    Convenience function to get an authenticated service object.
    Returns the service if successful, None otherwise.
    """
    try:
        auth = GooglePhotosAuth()
        if auth.authenticate():
            return auth.get_service()
        return None
    except Exception as e:
        logger.error(f"Failed to get authenticated service: {e}")
        return None

if __name__ == "__main__":
    # Test authentication when run directly
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Google Photos API authentication...")
    auth = GooglePhotosAuth()
    
    if auth.authenticate():
        print("✅ Authentication successful!")
        
        if auth.test_connection():
            print("✅ API connection test successful!")
            print("You're ready to use the Google Photos API.")
        else:
            print("❌ API connection test failed.")
    else:
        print("❌ Authentication failed.")
        print("Please check your credentials.json file and internet connection.")