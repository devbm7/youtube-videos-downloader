import os
import json
import yt_dlp
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, fields
import tempfile
from pathlib import Path
import re

from yt_dlp.utils import check_executable
from enum import Enum

# Configure logging
def setup_logging():
    """Setup logging configuration"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'youtube_downloader.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

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


class YtDlpConfigBuilder:
    """Builder class for yt-dlp configurations"""
    
    def __init__(self):
        self.config = {}
    
    def with_quiet_mode(self, quiet: bool = True) -> 'YtDlpConfigBuilder':
        """Enable or disable quiet mode"""
        self.config['quiet'] = quiet
        self.config['no_warnings'] = quiet
        return self
    
    def with_output_template(self, template: str) -> 'YtDlpConfigBuilder':
        """Set output template"""
        self.config['outtmpl'] = template
        return self
    
    def with_format_selector(self, format_selector: str) -> 'YtDlpConfigBuilder':
        """Set format selector"""
        self.config['format'] = format_selector
        return self
    
    def with_progress_hook(self, hook: Callable) -> 'YtDlpConfigBuilder':
        """Add progress hook"""
        if 'progress_hooks' not in self.config:
            self.config['progress_hooks'] = []
        self.config['progress_hooks'].append(hook)
        return self
    
    def with_single_video_mode(self) -> 'YtDlpConfigBuilder':
        """Enable single video mode (no playlist)"""
        self.config['noplaylist'] = True
        return self
    
    def with_temp_dir(self, temp_dir: str) -> 'YtDlpConfigBuilder':
        """Set temporary directory"""
        self.config['paths'] = {'tempdir': temp_dir}
        return self
    
    def with_postprocessors(self, postprocessors: List[Dict]) -> 'YtDlpConfigBuilder':
        """Add postprocessors"""
        self.config['postprocessors'] = postprocessors
        return self
    
    def with_merge_format(self, format_name: str = 'mp4') -> 'YtDlpConfigBuilder':
        """Set merge output format"""
        self.config['merge_output_format'] = format_name
        return self
    
    def with_extract_info_only(self) -> 'YtDlpConfigBuilder':
        """Configure for info extraction only"""
        self.config['listformats'] = False
        return self
    
    def with_validation_mode(self) -> 'YtDlpConfigBuilder':
        """Configure for URL validation"""
        self.config['extract_flat'] = True
        self.config['simulate'] = True
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build and return the configuration"""
        return self.config.copy()


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
        logger.info(f"YouTubeDownloader initialized with download path: {self.download_path}")

    def set_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """Set a callback function to receive progress updates"""
        self.progress_callback = callback
        logger.debug("Progress callback set")

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

    def sanitize_filename(self, title: str) -> str:
        """
        Sanitize title for use as filename by removing/replacing invalid characters
        
        Args:
            title: Original title string
            
        Returns:
            Sanitized filename string
        """
        # Remove or replace invalid filename characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', title)
        # Replace multiple spaces/underscores with single underscore
        sanitized = re.sub(r'[_\s]+', '_', sanitized)
        # Remove leading/trailing whitespace and underscores
        sanitized = sanitized.strip('_').strip()
        # Limit length to avoid filesystem issues
        return sanitized[:200] if len(sanitized) > 200 else sanitized

    def generate_output_template(self, url: str, custom_filename: Optional[str] = None) -> str:
        """
        Generate output template for yt-dlp
        
        Args:
            url: Video URL (used to fetch title if custom_filename is None)
            custom_filename: Custom filename to use
            
        Returns:
            Output template string
        """
        if custom_filename:
            return str(self.download_path / custom_filename)
        
        try:
            # Get video info to create default filename
            video_info = self.get_video_info(url)
            clean_title = self.sanitize_filename(video_info.title)
            return str(self.download_path / f"{clean_title}.%(ext)s")
        except Exception as e:
            logger.warning(f"Could not fetch video info for default filename: {e}")
            # Fallback template using video ID
            return str(self.download_path / "%(id)s.%(ext)s")

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
        logger.info(f"Extracting video info for URL: {url}")
        
        ydl_opts = (YtDlpConfigBuilder()
                   .with_quiet_mode()
                   .with_extract_info_only()
                   .build())

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

                logger.debug(f"Available keys in yt-dlp info: {list(info.keys())}")

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

                # Create VideoInfo with defensive approach
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

                logger.info(f"Successfully extracted info for video: {video_info_args.get('title', 'Unknown')}")
                return VideoInfo(**video_info_args) # Unpack the dictionary into keyword arguments

        except Exception as e:
            logger.error(f"Failed to extract video info: {str(e)}")
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
        logger.info(f"Getting available formats for URL: {url}")
        video_info = self.get_video_info(url)
        if not video_info.formats:
            logger.error("No downloadable formats found")
            raise Exception("No downloadable formats found for this video.")
        logger.info(f"Found {len(video_info.formats)} available formats")
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
        logger.info(f"Getting quality options for URL: {url}")
        
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
            
            logger.debug(f"Available video heights: {sorted(available_heights, reverse=True)}")
            
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
            
            logger.info(f"Found {len(available_options)} quality options")
            return available_options
            
        except Exception as e:
            logger.error(f"Failed to get quality options: {str(e)}")
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
        logger.info(f"Starting download by format ID: {format_id} for URL: {url}")
        
        # First, get video info to validate URL and format_id existence
        try:
            video_info = self.get_video_info(url)
            available_format_ids = [f['format_id'] for f in video_info.formats]
            if format_id not in available_format_ids:
                 logger.error(f"Invalid format ID: {format_id}")
                 raise Exception(f"Invalid format ID: {format_id}. Available IDs: {', '.join(available_format_ids)}")
        except Exception as e:
            logger.error(f"Validation failed before download: {str(e)}")
            raise Exception(f"Validation failed before download: {str(e)}")

        # Generate output template
        output_template = self.generate_output_template(url, output_filename)
        if not output_filename:
            # Find the selected format to get the correct extension
            selected_format = next((f for f in video_info.formats if f['format_id'] == format_id), None)
            # Use the format extension in template
            if selected_format and selected_format.get('ext'):
                output_template = output_template.replace('.%(ext)s', f".%(ext)s")

        ydl_opts = (YtDlpConfigBuilder()
                   .with_format_selector(format_id)
                   .with_output_template(output_template)
                   .with_progress_hook(self._progress_hook)
                   .with_single_video_mode()
                   .with_temp_dir(str(self.download_path / 'temp'))
                   .with_postprocessors([])  # Initialize empty list
                   .build())

        # Check if the selected format is audio-only and add postprocessor if needed
        selected_format = next((f for f in video_info.formats if f['format_id'] == format_id), None)
        if selected_format and selected_format.get('vcodec') == 'none' and selected_format.get('acodec') != 'none':
             # Add postprocessor to ensure it's an audio file
             ydl_opts['postprocessors'].append({
                 'key': 'FFmpegExtractAudio',
                 'preferredcodec': 'best', # Extract audio in the best available codec
                 'preferredquality': '0', # Highest quality
                 'nopostoverwrites': False, # Allow overwriting if necessary
             })
             logger.info("Added audio extraction postprocessor for audio-only format")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # extract_info with download=True returns info about the downloaded file(s)
                info = ydl.extract_info(url, download=True)

                # The final filepath is usually available in the info dictionary after download and postprocessing
                downloaded_file_path = info.get('filepath')

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                     logger.info(f"Download completed successfully: {downloaded_file_path}")
                     return downloaded_file_path
                else:
                    # Fallback: Try to construct the expected path based on the output template and info
                    logger.warning("Could not get exact 'filepath' from yt-dlp info. Estimating based on output template.")
                    try:
                        # This attempts to predict the final filename after postprocessing
                        estimated_path = ydl.prepare_filename(info)
                        if os.path.exists(estimated_path):
                             logger.info(f"Download completed successfully (estimated path): {estimated_path}")
                             return estimated_path
                        else:
                             raise Exception("Estimated file path does not exist.")
                    except Exception as e_prepare:
                         logger.error(f"Could not determine final downloaded file path: {e_prepare}")
                         raise Exception(f"Could not determine final downloaded file path: {e_prepare}")

        except Exception as e:
            logger.error(f"Download failed: {str(e)}")
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
        logger.info(f"Starting download by quality: {quality_name} for URL: {url}")
        
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
                logger.error(f"Quality '{quality_name}' not available")
                raise Exception(f"Quality '{quality_name}' not available. Available qualities: {', '.join(available_qualities)}")
            
            logger.info(f"Selected quality option: {selected_option['name']}")
            return self._download_with_format_selector(url, selected_option['format_selector'], output_filename)
            
        except Exception as e:
            logger.error(f"Download by quality failed: {str(e)}")
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
        logger.info(f"Starting best quality download for URL: {url}")
        
        try:
            # Get available quality options
            quality_options = self.get_available_quality_options(url)
            
            # Filter out audio-only option and find the highest quality
            video_options = [opt for opt in quality_options if opt['height'] > 0]
            
            if not video_options:
                logger.error("No video formats available for this URL")
                raise Exception("No video formats available for this URL.")
            
            # Select the best quality (first in the list as they're ordered by quality)
            best_quality = video_options[0]
            
            logger.info(f"Selected best available quality: {best_quality['name']} (actual height: {best_quality['actual_height']}px)")
            
            return self._download_with_format_selector(url, best_quality['format_selector'], output_filename)
            
        except Exception as e:
            logger.error(f"Best quality download failed: {str(e)}")
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
        logger.info(f"Starting download with format selector: {format_selector}")
        
        # First, check if FFmpeg is available, as it's required for merging
        if check_executable('ffmpeg') is None:
             logger.error("FFmpeg not found - required for merging video and audio streams")
             raise RuntimeError("FFmpeg is not found. It is required to merge video and audio streams. Please install FFmpeg.")

        # Generate output template
        output_template = self.generate_output_template(url, output_filename)

        ydl_opts = (YtDlpConfigBuilder()
                   .with_format_selector(format_selector)
                   .with_output_template(output_template)
                   .with_progress_hook(self._progress_hook)
                   .with_single_video_mode()
                   .with_temp_dir(str(self.download_path / 'temp'))
                   .with_merge_format('mp4')
                   .with_postprocessors([
                       {
                           'key': 'FFmpegVideoConvertor',
                           'preferedformat': 'mp4',
                       },
                   ])
                   .build())

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # extract_info with download=True will trigger download and postprocessing (merging)
                info = ydl.extract_info(url, download=True)

                # The final filepath is usually available in the info dictionary after download and postprocessing
                downloaded_file_path = info.get('filepath')

                if downloaded_file_path and os.path.exists(downloaded_file_path):
                     logger.info(f"Download with format selector completed successfully: {downloaded_file_path}")
                     return downloaded_file_path
                else:
                    # Fallback: Try to construct the expected path based on the output template and info
                    logger.warning("Could not get exact 'filepath' from yt-dlp info after processing. Estimating.")
                    try:
                        # This attempts to predict the final filename after postprocessing
                        estimated_path = ydl.prepare_filename(info)
                        if os.path.exists(estimated_path):
                             logger.info(f"Download completed successfully (estimated path): {estimated_path}")
                             return estimated_path
                        else:
                             raise Exception("Estimated file path does not exist after processing.")
                    except Exception as e_prepare:
                         logger.error(f"Could not determine final downloaded file path: {e_prepare}")
                         raise Exception(f"Could not determine final downloaded file path: {e_prepare}")

        except Exception as e:
            logger.error(f"Download with format selector failed: {str(e)}")
            raise Exception(f"Download failed: {str(e)}")

    def validate_url(self, url: str) -> bool:
        """
        Validate if URL is a valid YouTube URL or a URL supported by yt-dlp
        Args:
            url: URL to validate
        Returns:
            True if valid, False otherwise
        """
        logger.info(f"Validating URL: {url}")
        
        try:
            # Use extract_flat=True and no_download=True for faster validation
            ydl_opts = (YtDlpConfigBuilder()
                       .with_quiet_mode()
                       .with_validation_mode()
                       .build())
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=False) # download=False is crucial for validation
                logger.info(f"URL validation successful: {url}")
                return True
        except Exception as e:
            # Any exception during info extraction means the URL is likely not supported or invalid
            logger.warning(f"URL validation failed: {url} - {str(e)}")
            return False

    def get_supported_sites(self) -> List[str]:
        """Get list of supported sites from yt-dlp"""
        logger.info("Getting list of supported sites")
        try:
            # Use a more efficient way to list extractor names
            sites = [ie.IE_NAME for ie in yt_dlp.extractor.gen_extractors() if ie.suitable('http://test.com/')]
            logger.info(f"Found {len(sites)} supported sites")
            return sites
        except Exception as e:
            logger.error(f"Failed to get supported sites: {str(e)}")
            return []


# Factory function for easy instantiation
def create_downloader(download_path: str = "./downloads") -> YouTubeDownloader:
    """
    Factory function to create a YouTubeDownloader instance
    Args:
        download_path: Directory where files will be downloaded
    Returns:
        YouTubeDownloader instance
    """
    logger.info(f"Creating YouTubeDownloader instance with path: {download_path}")
    return YouTubeDownloader(download_path)