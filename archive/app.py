import streamlit as st
import yt_dlp as youtube_dl
import os
from pathlib import Path
from PIL import Image
from io import BytesIO
import requests

# Function to fetch video/playlist details and formats
def fetch_details(video_url):
    ydl_opts = {'quiet': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        if 'entries' in info:  # Playlist detected
            videos = [{"title": entry['title'], "url": entry['url']} for entry in info['entries']]
            return {"type": "playlist", "videos": videos}
        else:  # Single video
            formats = [
                {
                    "format_id": f["format_id"],
                    "ext": f["ext"],
                    "resolution": f.get("resolution", "audio only" if "audio" in f["format"] else "unknown"),
                    "filesize": f.get("filesize", None)
                }
                for f in info["formats"] if f.get("format_id") and f.get("ext")
            ]
            return {"type": "video", "title": info["title"], "thumbnail": info["thumbnail"], "formats": formats}

# Function to download video/audio
def download_media(video_url, format_id, is_audio, progress_callback):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best' if not is_audio else format_id,
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'progress_hooks': [progress_callback],
    }
    if is_audio:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    try:
        os.makedirs('downloads', exist_ok=True)
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(video_url, download=True)
            title = result.get('title', 'Unknown Title')
            filepath = Path(ydl.prepare_filename(result)).resolve()
            return f"Download successful: {title}", filepath
    except Exception as e:
        return f"Error: {e}", None

# Streamlit app
st.title("Enhanced YouTube Downloader with Playlist Support")
st.write("Enter a YouTube URL to preview and download videos/audio.")

# Input field for video URL
video_url = st.text_input("YouTube Video or Playlist URL:")

if video_url.strip():
    with st.spinner("Fetching details..."):
        try:
            details = fetch_details(video_url)

            if details['type'] == 'playlist':
                st.success("Playlist detected! Select videos to download.")
                video_selection = st.multiselect(
                    "Videos in Playlist:",
                    [v['title'] for v in details['videos']]
                )
                selected_videos = [v for v in details['videos'] if v['title'] in video_selection]

                if st.button("Download Selected Videos"):
                    for video in selected_videos:
                        st.write(f"Downloading: {video['title']}")
                        progress = st.progress(0)
                        status_text = st.empty()

                        def playlist_progress_hook(d):
                            if d['status'] == 'downloading':
                                total_bytes = d.get('total_bytes', 1)
                                downloaded_bytes = d.get('downloaded_bytes', 0)
                                progress.progress(downloaded_bytes / total_bytes)
                                status_text.text(f"Downloading: {downloaded_bytes / total_bytes:.2%}")

                        status, _ = download_media(video['url'], "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best", False, playlist_progress_hook)
                        st.success(status)
            else:  # Single video
                st.success(f"Video found: {details['title']}")
                response = requests.get(details['thumbnail'])
                thumbnail = Image.open(BytesIO(response.content))
                st.image(thumbnail, caption=details['title'], use_column_width=True)

                # Audio or Video option
                is_audio = st.checkbox("Download audio only (MP3)?")

                # Dropdown for format selection
                format_options = [
                    f"{f['resolution']} ({f['ext']}) - {f['filesize'] or 'Unknown size'} bytes"
                    for f in details['formats']
                ]
                selected_format = st.selectbox("Select Format:", options=format_options, index=0)
                selected_format_id = details['formats'][format_options.index(selected_format)]["format_id"]

                # Progress bar
                progress = st.progress(0)
                status_text = st.empty()

                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total_bytes = d.get('total_bytes', 1)
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        progress.progress(downloaded_bytes / total_bytes)
                        speed = d.get('speed', 0)
                        eta = d.get('eta', 0)
                        status_text.text(f"Speed: {speed / 1024:.2f} KB/s | ETA: {eta}s")

                if st.button("Download"):
                    with st.spinner("Downloading..."):
                        status, filepath = download_media(video_url, selected_format_id, is_audio, progress_hook)
                        if filepath:
                            st.success(status)
                            with open(filepath, "rb") as f:
                                st.download_button(
                                    label="Download File",
                                    data=f,
                                    file_name=filepath.name,
                                    mime=f"audio/mp3" if is_audio else f"video/{filepath.suffix.lstrip('.')}"
                                )
                        else:
                            st.error(status)
        except Exception as e:
            st.error(f"Error fetching details: {e}")
