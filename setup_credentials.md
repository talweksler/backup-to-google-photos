# Google Photos API - Setup Instructions

Follow these steps to set up Google Photos API access for the backup tool.

## Prerequisites
- A Google account
- Access to Google Cloud Console

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Click "New Project"
4. Enter a project name (e.g., "Photos Backup Tool")
5. Click "Create"
6. Wait for the project to be created and make sure it's selected

## Step 2: Enable Google Photos Library API

1. In the Google Cloud Console, go to "APIs & Services" → "Library"
2. Search for "Photos Library API"
3. Click on "Photos Library API" in the results
4. Click the "ENABLE" button
5. Wait for the API to be enabled

## Step 3: Configure OAuth Consent Screen

1. Go to "APIs & Services" → "OAuth consent screen"
2. Choose "External" user type (unless you have a Google Workspace account)
3. Click "CREATE"
4. Fill in the required fields:
   - **App name**: Photos Backup Tool
   - **User support email**: Your email
   - **Developer contact information**: Your email
5. Click "SAVE AND CONTINUE"
6. On the "Data Access" page:
   - Click "ADD OR REMOVE SCOPES"
   - Search for and select these two scopes:
     - `https://www.googleapis.com/auth/photoslibrary.appendonly` (upload media and create albums)
     - `https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata` (list and edit albums created by this app)
   - Do NOT add deprecated scopes like `photoslibrary`, `photoslibrary.readonly`, or `photoslibrary.sharing`
   - Click "UPDATE"
   - Click "SAVE AND CONTINUE"
7. On the "Test users" page:
   - Click "ADD USERS"
   - Add your email address
   - Click "ADD"
   - Click "SAVE AND CONTINUE"
8. Review the summary and click "BACK TO DASHBOARD"

## Step 4: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "CREATE CREDENTIALS" → "OAuth client ID"
3. Select "Desktop app" as the Application type
4. Name it "Photos Backup Desktop Client"
5. Click "CREATE"
6. In the popup, click "DOWNLOAD JSON"
7. Save the file as `credentials.json` in the project root directory

## Step 5: Verify Your Setup

Your `credentials.json` should look similar to this structure:
```json
{
  "installed": {
    "client_id": "xxxxxxxxxxxxx.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "xxxxxxxxxxxxx",
    "redirect_uris": ["http://localhost"]
  }
}
```

## Step 6: First Authentication

When you run the script for the first time:
1. It will open your default browser
2. You'll be asked to sign in to your Google account
3. You'll see a warning "Google hasn't verified this app" - click "Continue"
4. Grant permission for the app to:
   - "Add to your Google Photos library"
   - "Edit items added by this app"
5. The browser will show "The authentication flow has completed"
6. The script will save the token in `token.json` for future use

## Important Security Notes

⚠️ **NEVER commit these files to version control:**
- `credentials.json` - Contains your OAuth client credentials
- `token.json` - Contains your access token

Add both to your `.gitignore` file:
```
credentials.json
token.json
.backup_states/
```

## Quota Limits

The Google Photos Library API has the following limits:
- **Daily quota**: 10,000 requests per day
- **Per-user quota**: 10,000 requests per day per user
- **Quota resets**: Daily at midnight Pacific Time

## Troubleshooting

### "Access blocked: Authorization Error"
- Make sure you've added your email as a test user in the OAuth consent screen

### "Quota exceeded" error
- Wait until the next day for quota reset
- Check the Google Cloud Console for current usage

### "Invalid scope" error
- Ensure you're using ONLY these two scopes:
  - `photoslibrary.appendonly`
  - `photoslibrary.edit.appcreateddata`
- Do NOT use deprecated scopes (`photoslibrary`, `photoslibrary.readonly`, `photoslibrary.sharing`)
- Note: Apps can now only access albums and media they created

### "Credentials file not found"
- Make sure `credentials.json` is in the project root
- Check the filename is exactly `credentials.json`

## Monitoring Usage

You can monitor your API usage:
1. Go to Google Cloud Console
2. Navigate to "APIs & Services" → "Metrics"
3. Select "Photos Library API"
4. View request counts and quota usage

## Revoking Access

If you need to revoke access:
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Click on "Third-party apps with account access"
3. Find "Photos Backup Tool"
4. Click "Remove Access"

## Support

For API-specific issues, refer to:
- [Google Photos Library API Documentation](https://developers.google.com/photos/library/guides/get-started)
- [Google Photos API Support](https://developers.google.com/photos/support)