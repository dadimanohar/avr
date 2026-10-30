# Daily AI News Shorts — free-first automation

This repository is designed to run on GitHub Actions (hosted runner), not on a paid server or your own computer.

## What it does
- Runs daily at 09:00 Asia/Kolkata (03:30 UTC) and supports manual runs.
- Reads official AI-company RSS feeds.
- Uses Gemini API free-tier text generation to draft a short in Indian Professional English.
- Rejects a run if it has no supplied source URLs, an unsupported response, or an unsuitable script length.
- Uses offline `espeak-ng` narration and FFmpeg to render a 720x1280 MP4 with subtitles.
- Uploads the video using YouTube Data API OAuth.
- Saves the rendered MP4, script, metadata and upload receipt as a 7-day Actions artifact.

## Required GitHub Actions secrets
Add these in repository Settings → Secrets and variables → Actions → New repository secret:
- `GEMINI_API_KEY` — Google AI Studio API key (free-tier eligible model).
- `YOUTUBE_CLIENT_ID` — OAuth 2.0 Client ID from Google Cloud.
- `YOUTUBE_CLIENT_SECRET` — matching OAuth client secret.
- `YOUTUBE_REFRESH_TOKEN` — refresh token authorized by the channel owner with scope `https://www.googleapis.com/auth/youtube.upload`.

Optional repository variable:
- `YOUTUBE_PRIVACY` — `public`, `unlisted` or `private`; defaults to private until Google verifies the API project.

Never commit keys or tokens into this repository or send them in chat.

## One-time Google setup (no payment card required for YouTube Data API)
1. Open Google Cloud Console and create/select a project.
2. Enable **YouTube Data API v3**.
3. Configure the OAuth consent screen. Add your Google account as a test user if the app is in Testing.
4. Create an OAuth Client ID. For the easiest one-time refresh-token setup, use Google's OAuth 2.0 Playground with your own OAuth client credentials and the YouTube upload scope. Exchange the authorization code for a refresh token. Do not share it with anyone; paste it only into the GitHub Actions secret field.
5. Open Google AI Studio and create a Gemini API key. Use only a model with an active free tier for your account. Do not enable billing.

Google may restrict uploads from unverified API projects to private visibility. If YouTube rejects public upload, set `YOUTUBE_PRIVACY=private` until Google verifies the API project. Do not assume a successful API upload means the video is public; verify the resulting Shorts URL.

## Test it without credentials
A separate Pipeline Smoke Test runs on relevant code changes. It fetches an official RSS item, generates a clearly labelled demo narration, renders the MP4 offline, validates the video streams and stores a 7-day artifact. It does not call Gemini or upload to YouTube. Download the `daily-shorts-pipeline-demo` artifact from the Actions run.

## Production test
1. Add all four secrets.
2. Open Actions → Daily AI News Short → Run workflow.
3. Inspect the run logs and download the `daily-short-<run>` artifact.
4. Verify the video and the resulting YouTube URL before relying on the daily schedule.

## Honest limitations
- The offline eSpeak NG voice is synthetic and may not sound like a natural Indian presenter. The runner selects `en-in` when installed and falls back to `en`.
- The visuals are a designed motion title card with captions, not generated cinematic footage.
- RSS discovery alone is not full fact-checking. The script uses official feed headlines and source links; review important claims and source pages.
- Gemini free-tier limits and availability can change. A quota or model error stops the workflow without uploading.
- GitHub Actions free minutes and usage policies apply. Public repositories have different runner allowances from private repositories.
- YouTube API OAuth setup and any verification requirements are controlled by Google.
