import streamlit as st
import os
import time
from pathlib import Path
import tempfile
from api import YouTubeDownloader, DownloadFormat, VideoInfo, DownloadProgress

# Page configuration
st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="📹",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        margin-bottom: 1rem !important;
    }
    .subheader {
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        margin-top: 1rem !important;
    }
    .video-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        background-color: #f8f9fa;
        margin-bottom: 1rem;
    }
    .format-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 0.5rem;
        margin: 0.3rem 0;
        cursor: pointer;
    }
    .format-card:hover {
        background-color: #f0f0f0;
    }
    .format-selected {
        border: 2px solid #ff4b4b;
        background-color: #fff1f1;
    }
    .stButton button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'downloader' not in st.session_state:
    # Create downloads directory in temp folder for demo
    downloads_dir = Path(tempfile.gettempdir()) / "youtube_downloads"
    st.session_state.downloader = YouTubeDownloader(str(downloads_dir))
    st.session_state.download_progress = None
    st.session_state.video_info = None
    st.session_state.formats = None
    st.session_state.is_downloading = False
    st.session_state.selected_format_id = None
    st.session_state.last_download_path = None

def progress_callback(progress: DownloadProgress):
    """Callback function to update progress in session state"""
    st.session_state.download_progress = progress

# Set up progress callback
st.session_state.downloader.set_progress_callback(progress_callback)

# Main header
st.markdown('<p class="main-header">📹 YouTube Video Downloader</p>', unsafe_allow_html=True)
st.markdown("Download videos and audio from YouTube with high quality options.")

# Main content area with tabs
tab1, tab2, tab3 = st.tabs(["📥 Download", "ℹ️ Video Details", "📂 Downloads"])

with tab1:
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown('<p class="subheader">Enter YouTube URL</p>', unsafe_allow_html=True)
        
        # URL input
        url_input = st.text_input(
            "Paste YouTube URL here:",
            placeholder="https://www.youtube.com/watch?v=...",
            help="Support for YouTube videos and other platforms via yt-dlp"
        )
        
        # URL validation and info extraction
        if url_input:
            url_valid = st.session_state.downloader.validate_url(url_input)
            if not url_valid:
                st.error("⚠️ The URL appears to be invalid. Please enter a correct YouTube URL.")
            else:
                if 'video_info' not in st.session_state or not st.session_state.video_info or st.session_state.video_info.url != url_input:
                    with st.spinner("Fetching video information..."):
                        try:
                            video_info = st.session_state.downloader.get_video_info(url_input)
                            st.session_state.video_info = video_info
                            st.session_state.formats = video_info.formats
                            
                            # Get available quality options
                            quality_options = st.session_state.downloader.get_available_quality_options(url_input)
                            st.session_state.quality_options = quality_options
                            
                            st.success("✅ Video information loaded successfully!")
                        except Exception as e:
                            st.error(f"❌ Error fetching video details: {str(e)}")
        
        # Show download options if video info is available
        if st.session_state.video_info:
            st.markdown('<p class="subheader">Download Options</p>', unsafe_allow_html=True)
            
            # Quality selection
            if hasattr(st.session_state, 'quality_options'):
                st.markdown("### Select Quality")
                quality_col1, quality_col2 = st.columns([2, 1])
                
                with quality_col1:
                    selected_quality = st.selectbox(
                        "Choose video quality:",
                        options=[opt['name'] for opt in st.session_state.quality_options],
                        format_func=lambda x: f"{x} - {next(opt['description'] for opt in st.session_state.quality_options if opt['name'] == x)}"
                    )
                
                with quality_col2:
                    if st.button("⬇️ Download Selected Quality", use_container_width=True):
                        with st.spinner(f"Downloading {selected_quality}..."):
                            try:
                                st.session_state.is_downloading = True
                                downloaded_file = st.session_state.downloader.download_by_quality(
                                    url_input,
                                    selected_quality
                                )
                                st.session_state.last_download_path = downloaded_file
                                st.success(f"✅ Download complete!")
                            except Exception as e:
                                st.error(f"❌ Download failed: {str(e)}")
                            finally:
                                st.session_state.is_downloading = False
            
            # Quick download options
            st.markdown("### Quick Download Options")
            quick_col1, quick_col2 = st.columns(2)
            
            with quick_col1:
                if st.button("🎬 Best Available Quality", use_container_width=True):
                    with st.spinner("Starting download with best available quality..."):
                        try:
                            st.session_state.is_downloading = True
                            downloaded_file = st.session_state.downloader.download_best_quality_with_audio(url_input)
                            st.session_state.last_download_path = downloaded_file
                            st.success(f"✅ Download complete!")
                        except Exception as e:
                            st.error(f"❌ Download failed: {str(e)}")
                        finally:
                            st.session_state.is_downloading = False
            
            with quick_col2:
                if st.button("🎵 Audio Only", use_container_width=True):
                    with st.spinner("Starting audio download..."):
                        try:
                            st.session_state.is_downloading = True
                            downloaded_file = st.session_state.downloader.download_by_quality(
                                url_input,
                                "Audio Only"
                            )
                            st.session_state.last_download_path = downloaded_file
                            st.success(f"✅ Download complete!")
                        except Exception as e:
                            st.error(f"❌ Download failed: {str(e)}")
                        finally:
                            st.session_state.is_downloading = False
            
            # Custom filename option
            custom_filename = st.text_input(
                "Custom filename (optional):",
                placeholder="Enter a custom filename (without extension)"
            )
    
    with col2:
        if st.session_state.formats:
            st.markdown('<p class="subheader">Available Formats</p>', unsafe_allow_html=True)
            
            # Filter options
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                show_video = st.checkbox("Video", value=True)
            with filter_col2:
                show_audio = st.checkbox("Audio", value=True)
            with filter_col3:
                show_combined = st.checkbox("Combined", value=True)
            
            # Format display in scrollable container
            st.markdown('<div style="max-height: 400px; overflow-y: auto;">', unsafe_allow_html=True)
            
            for format in st.session_state.formats:
                # Filter formats based on checkboxes
                has_video = format.get('vcodec') != 'none'
                has_audio = format.get('acodec') != 'none'
                
                if (has_video and has_audio and show_combined) or \
                   (has_video and not has_audio and show_video) or \
                   (not has_video and has_audio and show_audio):
                    
                    # Format card
                    format_id = format.get('format_id')
                    is_selected = st.session_state.selected_format_id == format_id
                    card_class = "format-card format-selected" if is_selected else "format-card"
                    
                    st.markdown(f'<div class="{card_class}" id="format-{format_id}">', unsafe_allow_html=True)
                    
                    # Format details
                    format_type = "🎬 Video + Audio" if has_video and has_audio else "📹 Video only" if has_video else "🎵 Audio only"
                    resolution = f"{format.get('width')}x{format.get('height')}" if format.get('width') and format.get('height') else "N/A"
                    ext = format.get('ext', 'N/A')
                    size = f"{format.get('filesize', 0) / (1024*1024):.1f} MB" if format.get('filesize') else "Unknown"
                    
                    st.markdown(f"""
                    <div style="display:flex; justify-content:space-between;">
                        <div><b>{format_type}</b> ({format_id})</div>
                        <div>{ext.upper()}</div>
                    </div>
                    <div>
                        {resolution} • {format.get('format_note', '')} • {size}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Download format {format_id}", key=f"btn_{format_id}"):
                        st.session_state.selected_format_id = format_id
                        with st.spinner(f"Downloading format {format_id}..."):
                            try:
                                st.session_state.is_downloading = True
                                downloaded_file = st.session_state.downloader.download_video_by_format_id(
                                    url_input,
                                    format_id,
                                    custom_filename if custom_filename else None
                                )
                                st.session_state.last_download_path = downloaded_file
                                st.success(f"✅ Download complete!")
                            except Exception as e:
                                st.error(f"❌ Download failed: {str(e)}")
                            finally:
                                st.session_state.is_downloading = False
                    
                    st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

# Progress display
if st.session_state.is_downloading and st.session_state.download_progress:
    progress = st.session_state.download_progress
    
    st.markdown("---")
    st.markdown('<p class="subheader">⬬ Download Progress</p>', unsafe_allow_html=True)
    
    if progress.status == "downloading":
        # Progress bar
        progress_bar = st.progress(min(progress.percentage / 100, 1.0))
        
        # Progress info
        col_prog1, col_prog2, col_prog3 = st.columns(3)
        with col_prog1:
            st.metric("Progress", f"{progress.percentage:.1f}%")
        with col_prog2:
            if progress.speed:
                st.metric("Speed", progress.speed)
        with col_prog3:
            if progress.eta:
                st.metric("ETA", progress.eta)
        
        if progress.filename:
            st.text(f"Downloading: {Path(progress.filename).name}")
    
    elif progress.status == "merging":
        st.info("⏳ Merging video and audio streams... This may take a moment.")
        progress_bar = st.progress(1.0)  # Show full bar during merging
        
        if progress.filename:
            st.text(f"Creating: {Path(progress.filename).name}")
    
    elif progress.status == "finished":
        st.success("✅ Download completed!")
        st.session_state.is_downloading = False
        
        # Show download location and open folder button
        if st.session_state.last_download_path:
            file_path = Path(st.session_state.last_download_path)
            st.code(str(file_path))
            
            # Add download button for the file
            with open(file_path, 'rb') as f:
                file_data = f.read()
                st.download_button(
                    label="⬇️ Download File",
                    data=file_data,
                    file_name=file_path.name,
                    mime="application/octet-stream"
                )
            
            # Button to open containing folder (works on desktop)
            if st.button("📂 Open Containing Folder"):
                try:
                    # Try to open the folder containing the file
                    import subprocess
                    import platform
                    
                    folder_path = file_path.parent
                    
                    if platform.system() == "Windows":
                        subprocess.Popen(["explorer", folder_path])
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.Popen(["open", folder_path])
                    else:  # Linux
                        subprocess.Popen(["xdg-open", folder_path])
                except Exception as e:
                    st.error(f"Could not open folder: {str(e)}")
    
    elif progress.status == "error":
        st.error(f"❌ Download failed: {progress.error_message}")
        st.session_state.is_downloading = False

# Video Information Tab
with tab2:
    if st.session_state.video_info:
        video = st.session_state.video_info
        
        col_thumb, col_info = st.columns([1, 2])
        
        with col_thumb:
            if video.thumbnail:
                st.image(video.thumbnail, use_container_width=True)
        
        with col_info:
            st.markdown(f"## {video.title}")
            st.markdown(f"**Channel:** {video.uploader}")
            
            info_col1, info_col2 = st.columns(2)
            
            with info_col1:
                if video.upload_date:
                    # Format upload date (YYYYMMDD to YYYY-MM-DD)
                    if len(video.upload_date) >= 8:
                        formatted_date = f"{video.upload_date[0:4]}-{video.upload_date[4:6]}-{video.upload_date[6:8]}"
                        st.markdown(f"**Uploaded:** {formatted_date}")
                
                if video.duration:
                    minutes = video.duration // 60
                    seconds = video.duration % 60
                    st.markdown(f"**Duration:** {minutes}:{seconds:02d}")
            
            with info_col2:
                if video.view_count:
                    st.markdown(f"**Views:** {video.view_count:,}")
                
                st.markdown(f"**Video ID:** {video.id}")
        
        # Available qualities expander
        if hasattr(st.session_state, 'quality_options'):
            with st.expander("📊 Available Qualities", expanded=True):
                for option in st.session_state.quality_options:
                    st.markdown(f"**{option['name']}** - {option['description']}")
        
        # Description expander
        with st.expander("📝 Description", expanded=False):
            if video.description:
                st.text_area("", value=video.description, height=250, disabled=True)
            else:
                st.text("No description available.")
        
        # Format details expander
        with st.expander("🔍 Available Format Details", expanded=False):
            if st.session_state.formats:
                # Create a dataframe for better format display
                import pandas as pd
                
                # Extract relevant format information
                format_data = []
                for fmt in st.session_state.formats:
                    format_data.append({
                        "Format ID": fmt.get('format_id', 'N/A'),
                        "Extension": fmt.get('ext', 'N/A'),
                        "Resolution": f"{fmt.get('width', 'N/A')}x{fmt.get('height', 'N/A')}",
                        "Video Codec": fmt.get('vcodec', 'none'),
                        "Audio Codec": fmt.get('acodec', 'none'),
                        "Filesize (MB)": f"{fmt.get('filesize', 0) / (1024*1024):.1f}" if fmt.get('filesize') else "Unknown",
                        "Note": fmt.get('format_note', 'N/A')
                    })
                
                formats_df = pd.DataFrame(format_data)
                st.dataframe(formats_df, use_container_width=True)
            else:
                st.text("No format information available.")

# Downloads Tab
with tab3:
    st.markdown('<p class="subheader">Downloaded Files</p>', unsafe_allow_html=True)
    
    # Check downloads directory for files
    downloads_dir = Path(st.session_state.downloader.download_path)
    
    if downloads_dir.exists():
        files = list(downloads_dir.glob("*.*"))
        
        if files:
            # Display files in a table format
            file_data = []
            for file in files:
                file_size = file.stat().st_size / (1024*1024)  # MB
                mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file.stat().st_mtime))
                
                file_data.append({
                    "Filename": file.name,
                    "Size (MB)": f"{file_size:.2f}",
                    "Modified": mod_time,
                    "Path": str(file)
                })
            
            import pandas as pd
            files_df = pd.DataFrame(file_data)
            st.dataframe(files_df, use_container_width=True)
            
            # Add download buttons for each file
            st.markdown("### Download Files")
            for file in files:
                with open(file, 'rb') as f:
                    file_data = f.read()
                    st.download_button(
                        label=f"⬇️ Download {file.name}",
                        data=file_data,
                        file_name=file.name,
                        mime="application/octet-stream"
                    )
            
            # Option to clear downloads
            if st.button("🗑️ Clear Downloads Folder"):
                try:
                    for file in files:
                        try:
                            file.unlink()
                        except:
                            pass
                    st.success("Downloads folder cleared!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error clearing downloads: {str(e)}")
        else:
            st.info("No downloaded files found.")
    else:
        st.warning(f"Downloads directory {downloads_dir} does not exist.")

# Sidebar with information
with st.sidebar:
    st.header("ℹ️ About")
    st.info("""
    This YouTube Downloader uses yt-dlp to download videos from YouTube and other supported sites.
    
    - Select from available formats
    - Download audio-only files
    - High quality video with best audio
    """)
    
    st.markdown("### 🌟 Features")
    st.markdown("""
    - Format selection
    - Custom filename
    - Progress tracking
    - Download history
    """)
    
    # Current download location
    st.markdown("### 📁 Download Location")
    st.code(str(st.session_state.downloader.download_path))
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        <p>🚀 Powered by yt-dlp | Built with Streamlit</p>
        <p>⚠️ Please respect copyright laws and Terms of Service</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

# Auto-refresh for progress updates
if st.session_state.is_downloading:
    time.sleep(0.5)
    st.rerun()