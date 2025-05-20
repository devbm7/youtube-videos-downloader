# YouTube Downloader Project

A simple and efficient YouTube video downloader built with Python, yt-dlp, and Streamlit.

## Features

- 📹 Download single YouTube videos
- 📋 Support for playlists and channels
- 🎵 Multiple format options (MP4, MP3)
- 📊 Real-time download progress
- 📝 Video metadata extraction
- 🖥️ User-friendly Streamlit interface

## Installation

1. **Clone the repository:**

   ```bash
   git clone devbm7/youtube-downloader
   cd youtube-downloader
   ```
2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```
3. **Install FFmpeg (required for audio conversion):**

   **Windows:**

   - Download from https://ffmpeg.org/download.html
   - Add to PATH

   **macOS:**

   ```bash
   brew install ffmpeg
   ```

   **Linux:**

   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```

## Usage

### Running the Streamlit App

```bash
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

### Using the API Directly

```python
from youtube_downloader_api import YouTubeDownloader, DownloadFormat

# Initialize downloader
downloader = YouTubeDownloader("./downloads")

# Get video information
video_info = downloader.get_video_info("https://www.youtube.com/watch?v=VIDEO_ID")
print(f"Title: {video_info.title}")
print(f"Duration: {video_info.duration} seconds")

# Download video
downloaded_file = downloader.download_video(
    "https://www.youtube.com/watch?v=VIDEO_ID",
    DownloadFormat.MP4_720P
)
print(f"Downloaded: {downloaded_file}")
```

## Project Structure

```
youtube-downloader/
├── api.py    # Core API (framework-agnostic)
├── streamlit_app.py            # Streamlit web interface
├── requirements.txt            # Python dependencies
├── README.md                  # This file
└── downloads/                 # Default download directory
```

## API Reference

### YouTubeDownloader Class

#### Methods

- `get_video_info(url: str) -> VideoInfo`: Extract video metadata
- `get_playlist_info(url: str) -> List[VideoInfo]`: Extract playlist/channel info
- `download_video(url: str, format_choice: DownloadFormat) -> str`: Download video
- `validate_url(url: str) -> bool`: Validate YouTube URL
- `set_progress_callback(callback: Callable)`: Set progress update callback

#### Supported Formats

- `DownloadFormat.MP4_BEST`: Best quality MP4
- `DownloadFormat.MP4_720P`: 720p MP4
- `DownloadFormat.MP4_480P`: 480p MP4
- `DownloadFormat.MP3_BEST`: Audio only (MP3)

### Data Classes

#### VideoInfo

- `id`: Video ID
- `title`: Video title
- `description`: Video description
- `duration`: Duration in seconds
- `uploader`: Channel name
- `upload_date`: Upload date
- `view_count`: Number of views
- `thumbnail`: Thumbnail URL
- `formats`: Available formats
- `url`: Video URL

#### DownloadProgress

- `status`: Current status (downloading, finished, error)
- `percentage`: Download percentage (0-100)
- `speed`: Download speed
- `eta`: Estimated time remaining
- `filename`: Current filename
- `error_message`: Error message (if any)

## Future Development

This project is designed with modularity in mind. The core API (`api.py`) can be easily integrated into:

- **Web applications** (Flask, FastAPI, Django)
- **CLI tools**
- **Desktop applications** (tkinter, PyQt)
- **API services**

## Legal Notice

⚠️ **Important**: This tool is for educational purposes only. Please respect:

- YouTube's Terms of Service
- Copyright laws in your jurisdiction
- Content creators' rights

Only download content you have permission to download or that is available under appropriate licenses.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - The powerful video downloader library
- [Streamlit](https://streamlit.io/) - For the amazing web app framework
- [FFmpeg](https://ffmpeg.org/) - For media processing capabilities
