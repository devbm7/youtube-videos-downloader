import os
import json
import yt_dlp
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, fields # Import fields to inspect dataclass fields
import tempfile
from pathlib import Path

from yt_dlp.utils import check_executable
from enum import Enum

class DownloadFormat(Enum):
    """
    Supported download formats (kept for reference, but downloading by format_id is now preferred
    or using the new merged download method).
    These values correspond to yt-dlp format selectors.
    """
    MP4_BEST = "best[ext=mp4]" # May not include audio at all
    MP4_720P = "best[height<=720][ext=mp4]" # May not include best audio
    MP4_480P = "best[height<=480][ext=mp4]" # May not include best audio
    MP3_BEST = "bestaudio[ext=m4a]/bestaudio/best" # Extracts best audio and converts to mp3
    AUDIO_ONLY = "bestaudio/best" # Extracts best audio in its original format
    # New format selector for best video + best audio, to be merged
    BEST_VIDEO_AUDIO_MERGED = "bestvideo+bestaudio/best"


@dataclass
class VideoInfo:
    """Data class to store video information"""
    id: str
    title: str
    description: str
    duration: int
    uploader: str
    upload_date: str
    view_count: int
    thumbnail: str
    formats: List[Dict[str, Any]] # List of available formats with details
    url: str


@dataclass
class DownloadProgress:
    """Data class to store download progress information"""
    status: str  # downloading, finished, error, merging (new status for merging step)
    percentage: float # Percentage for downloading, might be 100% during merging
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None # Filename during download, final filename after merging
    error_message: Optional[str] = None
    # Added for more detailed progress during merging
    _hook_data: Optional[Dict[str, Any]] = None


class YouTubeDownloader:
    """Core YouTube downloader class using yt-dlp"""

    def __init__(self, download_path: str = "./downloads"):
        """
        Initialize the YouTube downloader

        Args:
            download_path: Directory where files will be downloaded
        """
        self.download_path = Path(download_path)
        self.download_path.mkdir(exist_ok=True)
        self.progress_callback: Optional[Callable[[DownloadProgress], None]] = None

    def set_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """Set a callback function to receive progress updates"""
        self.progress_callback = callback

    def _progress_hook(self, d: Dict[str, Any]):
        """Internal progress hook for yt-dlp"""
        if not self.progress_callback:
            return

        # yt-dlp sends different status updates, including 'downloading', 'finished', 'error',
        # and potentially others related to postprocessing like 'merging'.
        status = d.get('status', 'unknown')

        progress = DownloadProgress(
            status=status,
            percentage=0.0, # Default percentage
            _hook_data=d # Store the raw hook data for potential debugging or detailed info
        )

        if status == 'downloading':
            # Prefer using _total_bytes_estimate if available for more reliable percentage
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total_bytes and total_bytes > 0:
                progress.percentage = (d.get('downloaded_bytes', 0) / total_bytes) * 100
            elif '_percent_str' in d:
                # Extract percentage from string like "50.0%"
                percent_str = d['_percent_str'].strip().rstrip('%')
                try:
                    progress.percentage = float(percent_str)
                except (ValueError, AttributeError):
                    progress.percentage = 0.0

            progress.speed = d.get('_speed_str', None)
            progress.eta = d.get('_eta_str', None)
            progress.filename = d.get('filename', None)

        elif status == 'finished':
            progress.percentage = 100.0
            progress.filename = d.get('filename', None) # Final filename after all postprocessing

        elif status == 'error':
            progress.error_message = str(d.get('error', 'Unknown error'))
            # Attempt to get filename even on error
            progress.filename = d.get('filename', None)

        elif status == 'merging':
            # yt-dlp often reports merging progress, but it might not always be a percentage.
            # We can report 100% download completion and indicate merging is in progress.
            progress.percentage = 100.0 # Download is complete
            progress.filename = d.get('filename', None) # The file being merged into
            # You might parse d for more specific merging info if needed,
            # but the status 'merging' is usually sufficient to indicate this stage.


        # Always call the callback if set
        self.progress_callback(progress)


    def get_video_info(self, url: str) -> VideoInfo:
        """
        Extract video information including available formats without downloading

        Args:
            url: YouTube video URL

        Returns:
            VideoInfo object containing video metadata and formats

        Raises:
            Exception: If video information cannot be extracted
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'listformats': False, # We want the format list in the info dict
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Handle playlist/channel URLs - get first video for info
                if 'entries' in info:
                    if info['entries']:
                        # Recursively get full info for the first entry
                        # Use .get('url') first, fallback to constructing URL if missing
                        first_entry_url = info['entries'][0].get('url') or f"https://www.youtube.com/watch?v={info['entries'][0].get('id')}"
                        return self.get_video_info(first_entry_url)
                    else:
                        raise Exception("No videos found in playlist/channel")

                # --- Diagnostic Prints ---
                # print("\n--- Diagnostic Info ---")
                # print(f"Keys in yt-dlp info dictionary: {list(info.keys())}")
                # print(f"Expected fields in VideoInfo dataclass: {[f.name for f in fields(VideoInfo)]}")
                # print("--- End Diagnostic Info ---\n")
                # --- End Diagnostic Prints ---


                # Filter out formats that are missing essential info or are not downloadable streams
                # and add useful details for display.
                all_formats = []
                for f in info.get('formats', []):
                    if f.get('format_id') and f.get('url'): # Must have an ID and a URL
                        format_details = {
                            'format_id': f.get('format_id', 'N/A'),
                            'ext': f.get('ext', 'N/A'),
                            'quality': f.get('quality', 'N/A'), # This might be 'unknown' or similar
                            'format_note': f.get('format_note', 'N/A'), # Often contains resolution/audio info
                            'filesize': f.get('filesize', 0) or f.get('filesize_approx', 0), # Use approx if exact is missing
                            'resolution': f.get('resolution', 'N/A'), # Resolution string
                            'height': f.get('height'), # Height in pixels
                            'width': f.get('width'), # Width in pixels
                            'tbr': f.get('tbr'), # Total bitrate
                            'vcodec': f.get('vcodec', 'N/A'), # Video codec
                            'acodec': f.get('acodec', 'N/A'), # Audio codec
                            'fps': f.get('fps'), # Frames per second
                            'protocol': f.get('protocol', 'N/A'), # Protocol (e.g., https, m3u8, dash)
                            'dynamic_range': f.get('dynamic_range', 'N/A'), # HDR, SDR, etc.
                        }
                        all_formats.append(format_details)

                # Sort formats (optional, but helpful)
                # Prioritize video+audio, then video-only by resolution/bitrate, then audio-only by bitrate
                def sort_key(f):
                    is_video = f.get('vcodec') != 'none'
                    is_audio = f.get('acodec') != 'none'
                    height = f.get('height', 0) or 0
                    tbr = f.get('tbr', 0) or 0
                    # Sort order: video+audio > video-only > audio-only
                    # Within each category: highest resolution/bitrate first
                    if is_video and is_audio:
                        return (3, height, tbr)
                    elif is_video and not is_audio:
                        return (2, height, tbr)
                    elif not is_video and is_audio:
                        return (1, tbr)
                    else:
                        return (0,) # Unknown formats last

                sorted_formats = sorted(all_formats, key=sort_key, reverse=True)

                # --- Defensive VideoInfo Creation ---
                # Create a dictionary with arguments for VideoInfo, only including keys that
                # are both in the yt-dlp info and expected by the dataclass.
                # This is a workaround if the dataclass definition is somehow mismatched
                # or yt-dlp returns unexpected keys.
                video_info_args = {}
                expected_fields = {f.name for f in fields(VideoInfo)}
                for field_name in expected_fields:
                    # Use .get() with a default value appropriate for the field type
                    if field_name == 'formats':
                         video_info_args[field_name] = sorted_formats # Use the processed formats list
                    elif field_name == 'duration' or field_name == 'view_count':
                         video_info_args[field_name] = info.get(field_name, 0) # Default to 0 for numbers
                    elif field_name == 'url':
                         video_info_args[field_name] = url # Use the original URL
                    else:
                         video_info_args[field_name] = info.get(field_name, '') # Default to empty string for strings

                # Ensure all expected fields are present in the args dictionary, even if missing in info
                for field_name in expected_fields:
                    if field_name not in video_info_args:
                         # This should not happen with the loop above, but as a safeguard
                         if field_name == 'formats':
                              video_info_args[field_name] = []
                         elif field_name == 'duration' or field_name == 'view_count':
                              video_info_args[field_name] = 0
                         elif field_name == 'url':
                              video_info_args[field_name] = url # Use the original URL
                         else:
                              video_info_args[field_name] = ''


                return VideoInfo(**video_info_args) # Unpack the dictionary into keyword arguments
                # --- End Defensive VideoInfo Creation ---


        except Exception as e:
            raise Exception(f"Failed to extract video info: {str(e)}")

    def get_available_formats(self, url: str) -> List[Dict[str, Any]]:
        """
        Get a list of available download formats for a video.

        Args:
            url: YouTube video URL

        Returns:
            List of dictionaries, each representing a format with details.

        Raises:
            Exception: If video information cannot be extracted or no formats are found.
        """
        video_info = self.get_video_info(url)
        if not video_info.formats:
            raise Exception("No downloadable formats found for this video.")
        return video_info.formats

    def get_available_quality_options(self, url: str) -> List[Dict[str, Any]]:
        """
        Get available quality options for smart quality selection.
        Returns a list of quality options with their corresponding format selectors.

        Args:
            url: YouTube video URL

        Returns:
            List of dictionaries containing quality information and format selectors

        Raises:
            Exception: If video information cannot be extracted
        """
        try:
            video_info = self.get_video_info(url)
            
            # Define target resolutions in order of preference (highest to lowest)
            target_resolutions = [
                {'height': 2160, 'name': '4K (2160p)'},
                {'height': 1440, 'name': '1440p'},
                {'height': 1080, 'name': '1080p'},
                {'height': 720, 'name': '720p'},
                {'height': 480, 'name': '480p'},
                {'height': 360, 'name': '360p'},
            ]
            
            available_options = []
            
            # Find available video heights from formats
            available_heights = set()
            for fmt in video_info.formats:
                if fmt.get('height') and fmt.get('vcodec') != 'none':
                    available_heights.add(fmt['height'])
            
            # Create quality options for available resolutions
            for resolution in target_resolutions:
                target_height = resolution['height']
                
                # Check if this resolution or close to it is available
                # Allow some tolerance for slightly different heights (e.g., 1088 instead of 1080)
                closest_height = None
                for height in available_heights:
                    if abs(height - target_height) <= 50:  # 50px tolerance
                        if closest_height is None or abs(height - target_height) < abs(closest_height - target_height):
                            closest_height = height
                
                if closest_height:
                    # Create format selector for this quality
                    format_selector = f"bestvideo[height<={closest_height}]+bestaudio/best[height<={closest_height}]"
                    
                    available_options.append({
                        'name': resolution['name'],
                        'height': closest_height,
                        'actual_height': closest_height,
                        'format_selector': format_selector,
                        'description': f"{resolution['name']} with best audio"
                    })
            
            # Add audio-only option
            available_options.append({
                'name': 'Audio Only',
                'height': 0,
                'actual_height': 0,
                'format_selector': 'bestaudio/best',
                'description': 'Best quality audio only'
            })
            
            return available_options
            
        except Exception as e:
            raise Exception(f"Failed to get quality options: {str(e)}")

    def download_video_by_format_id(self, url: str, format_id: str,
                                    output_filename: Optional[str] = None) -> str:
        """
        Download a video from YouTube using a specific format ID.

        Args:
            url: YouTube video URL
            format_id: The ID of the format to download (obtained from get_available_formats)
            output_filename: Custom filename (optional)

        Returns:
            Path to the downloaded file

        Raises:
            Exception: If download fails or format ID is invalid
        """
        # First, get video info to validate URL and format_id existence
        try:
            video_info = self.get_video_info(url)
            available_format_ids = [f['format_id'] for f in video_info.formats]
            if format_id not in available_format_ids:
                 raise Exception(f"Invalid format ID: {format_id}. Available IDs: {', '.join(available_format_ids)}")
        except Exception as e:
            raise Exception(f"Validation failed before download: {str(e)}")


        # Set up output template
        if output_filename:
            output_template = str(self.download_path / output_filename)
        else:
            # Use video title and selected format extension for default filename
            # Find the selected format to get the correct extension
            selected_format = next((f for f in video_info.formats if f['format_id'] == format_id), None)
            # Default to mp4 if format not found or ext is missing (shouldn't happen after validation)
            ext = selected_format.get('ext', 'mp4') if selected_format and selected_format.get('ext') else 'mp4'

            title = video_info.title
            # Clean title for filename - replace invalid characters with underscores
            clean_title = "".join(c if c.isalnum() or c in (' ', '-', '_', '.') else '_' for c in title).strip()
            # Replace spaces with underscores for better file system compatibility
            clean_title = clean_title.replace(' ', '_')

            # Use %(ext)s to let yt-dlp handle the final extension based on the format
            output_template = str(self.download_path / f"{clean_title}.%(ext)s")


        ydl_opts = {
            'format': format_id, # Use the provided format_id
            'outtmpl': output_template,
            'progress_hooks': [self._progress_hook],
            'noplaylist': True, # Ensure only the single video is downloaded
            'postprocessors': [], # Initialize postprocessors list
            'paths': {'tempdir': str(self.download_path / 'temp')}, # Specify a temporary directory
        }

        # Check if the selected format is audio-only and add postprocessor if needed
        selected_format = next((f for f in video_info.formats if f['format_id'] == format_id), None)
        if selected_format and selected_format.get('vcodec') == 'none' and selected_format.get('acodec') != 'none':
             # Add postprocessor to ensure it's an audio file, e.g., mp3
             # yt-dlp often handles this automatically based on format, but explicitly adding is safer
             ydl_opts['postprocessors'].append({
                 'key': 'FFmpegExtractAudio',
                 'preferredcodec': 'best', # Extract audio in the best available codec
                 'preferredquality': '0', # Highest quality
                 'nopostoverwrites': False, # Allow overwriting if necessary
             })
             # Note: The output extension might change after postprocessing (e.g., to .mp3)
             # yt-dlp's %(ext)s in outtmpl handles this.


        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # extract_info with download=True returns info about the downloaded file(s)
                info = ydl.extract_info(url, download=True)

                # The final filepath is usually available in the info dictionary after download and postprocessing
                downloaded_file_path = info.get('filepath')

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                     return downloaded_file_path
                else:
                    # Fallback: Try to construct the expected path based on the output template and info
                    print("Warning: Could not get exact 'filepath' from yt-dlp info. Estimating based on output template and info.")
                    try:
                        # This attempts to predict the final filename after postprocessing
                        estimated_path = ydl.prepare_filename(info)
                        if os.path.exists(estimated_path):
                             return estimated_path
                        else:
                             raise Exception("Estimated file path does not exist.")
                    except Exception as e_prepare:
                         raise Exception(f"Could not determine final downloaded file path: {e_prepare}")


        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

    def download_by_quality(self, url: str, quality_name: str, output_filename: Optional[str] = None) -> str:
        """
        Download a video using one of the predefined quality options.

        Args:
            url: YouTube video URL
            quality_name: Name of the quality option (e.g., '1080p', '720p', '4K (2160p)', 'Audio Only')
            output_filename: Custom filename (optional)

        Returns:
            Path to the downloaded file

        Raises:
            Exception: If download fails or quality is not available
        """
        try:
            # Get available quality options
            quality_options = self.get_available_quality_options(url)
            
            # Find the requested quality
            selected_option = None
            for option in quality_options:
                if option['name'] == quality_name:
                    selected_option = option
                    break
            
            if not selected_option:
                available_qualities = [opt['name'] for opt in quality_options]
                raise Exception(f"Quality '{quality_name}' not available. Available qualities: {', '.join(available_qualities)}")
            
            return self._download_with_format_selector(url, selected_option['format_selector'], output_filename)
            
        except Exception as e:
            raise Exception(f"Download by quality failed: {str(e)}")

    def download_best_quality_with_audio(self, url: str, output_filename: Optional[str] = None) -> str:
        """
        Downloads the best available quality video with audio. 
        Automatically selects the highest available resolution among 4K, 1440p, 1080p, 720p.

        Args:
            url: YouTube video URL
            output_filename: Custom filename (optional). If not provided, a default will be generated.

        Returns:
            Path to the downloaded and merged file.

        Raises:
            Exception: If download or merging fails, or if no suitable streams are found.
            RuntimeError: If FFmpeg is not found, which is required for merging.
        """
        try:
            # Get available quality options
            quality_options = self.get_available_quality_options(url)
            
            # Filter out audio-only option and find the highest quality
            video_options = [opt for opt in quality_options if opt['height'] > 0]
            
            if not video_options:
                raise Exception("No video formats available for this URL.")
            
            # Select the best quality (first in the list as they're ordered by quality)
            best_quality = video_options[0]
            
            print(f"Selected best available quality: {best_quality['name']} (actual height: {best_quality['actual_height']}px)")
            
            return self._download_with_format_selector(url, best_quality['format_selector'], output_filename)
            
        except Exception as e:
            raise Exception(f"Best quality download failed: {str(e)}")

    def _download_with_format_selector(self, url: str, format_selector: str, output_filename: Optional[str] = None) -> str:
        """
        Internal method to download using a format selector string.

        Args:
            url: YouTube video URL
            format_selector: yt-dlp format selector string
            output_filename: Custom filename (optional)

        Returns:
            Path to the downloaded file

        Raises:
            Exception: If download fails
        """
        # First, check if FFmpeg is available, as it's required for merging
        if check_executable('ffmpeg') is None:
             raise RuntimeError("FFmpeg is not found. It is required to merge video and audio streams. Please install FFmpeg.")

        # Set up output template
        if output_filename:
            output_template = str(self.download_path / output_filename)
        else:
            # Get video info to create a default filename
            try:
                # Use get_video_info to fetch title for filename
                video_info = self.get_video_info(url)
                title = video_info.title
                # Clean title for filename - replace invalid characters with underscores
                clean_title = "".join(c if c.isalnum() or c in (' ', '-', '_', '.') else '_' for c in title).strip()
                # Replace spaces with underscores for better file system compatibility
                clean_title = clean_title.replace(' ', '_')
                # Use %(ext)s to let yt-dlp determine the final extension (usually .mp4 or .mkv)
                output_template = str(self.download_path / f"{clean_title}.%(ext)s")
            except Exception as e:
                # This exception is caught here to allow the download process to continue
                # even if fetching info for the default filename fails.
                print(f"Warning: Could not fetch video info for default filename. Using generic template. Error: {e}")
                # Fallback template using video ID
                output_template = str(self.download_path / "%(id)s.%(ext)s")

        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_template,
            'progress_hooks': [self._progress_hook],
            'noplaylist': True, # Ensure only the single video is downloaded
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor', # Ensure the final output is in a common format like mp4
                    'preferedformat': 'mp4',
                },
            ],
            # yt-dlp options for merging
            'merge_output_format': 'mp4', # Specify the output container format for merging
            'paths': {'tempdir': str(self.download_path / 'temp')}, # Specify a temporary directory
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # extract_info with download=True will trigger download and postprocessing (merging)
                info = ydl.extract_info(url, download=True)

                # The final filepath is usually available in the info dictionary after download and postprocessing
                downloaded_file_path = info.get('filepath')

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                     return downloaded_file_path
                else:
                    # Fallback: Try to construct the expected path based on the output template and info
                    print("Warning: Could not get exact 'filepath' from yt-dlp info after processing. Estimating based on output template and info.")
                    try:
                        # This attempts to predict the final filename after postprocessing
                        estimated_path = ydl.prepare_filename(info)
                        if os.path.exists(estimated_path):
                             return estimated_path
                        else:
                             raise Exception("Estimated file path does not exist after processing.")
                    except Exception as e_prepare:
                         raise Exception(f"Could not determine final downloaded file path: {e_prepare}")

        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

    def validate_url(self, url: str) -> bool:
        """
        Validate if URL is a valid YouTube URL or a URL supported by yt-dlp
        Args:
            url: URL to validate
        Returns:
            True if valid, False otherwise
        """
        try:
            # Use extract_flat=True and no_download=True for faster validation
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'simulate': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=False) # download=False is crucial for validation
                return True
        except Exception:
            # Any exception during info extraction means the URL is likely not supported or invalid
            return False

    def get_supported_sites(self) -> List[str]:
        """Get list of supported sites from yt-dlp"""
        # Use a more efficient way to list extractor names
        return [ie.IE_NAME for ie in yt_dlp.extractor.gen_extractors() if ie.suitable('http://test.com/')]


# Factory function for easy instantiation
def create_downloader(download_path: str = "./downloads") -> YouTubeDownloader:
    """
    Factory function to create a YouTubeDownloader instance
    Args:
        download_path: Directory where files will be downloaded
    Returns:
        YouTubeDownloader instance
    """
    return YouTubeDownloader(download_path)