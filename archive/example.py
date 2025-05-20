import sys
import os
from api import create_downloader, DownloadProgress, VideoInfo # Import necessary classes from your api.py

# Define a simple progress callback function
def my_progress_callback(progress: DownloadProgress):
    """Callback function to print download progress."""
    if progress.status == 'downloading':
        # Print progress on the same line
        # Use .get() with a default for safety in case speed or eta are missing
        speed_display = progress.speed if progress.speed is not None else 'N/A'
        eta_display = progress.eta if progress.eta is not None else 'N/A'
        # Use filename if available, otherwise show percentage
        if progress.filename:
             print(f"Downloading: {progress.filename} - {progress.percentage:.1f}% - Speed: {speed_display} - ETA: {eta_display}", end='\r')
        else:
             print(f"Downloading: {progress.percentage:.1f}% - Speed: {speed_display} - ETA: {eta_display}", end='\r')
        sys.stdout.flush() # Ensure the output is immediately visible
    elif progress.status == 'finished':
        print(f"\nDownload finished: {progress.filename}")
    elif progress.status == 'error':
        # Use .get() with a default for safety
        error_msg_display = progress.error_message if progress.error_message is not None else 'Unknown Error'
        print(f"\nDownload failed: {error_msg_display}")
        # Print filename on error if available
        if progress.filename:
             print(f"File involved: {progress.filename}")
    elif progress.status == 'merging':
        # yt-dlp merging status often includes the final filename
        merging_filename = progress.filename if progress.filename else '...'
        print(f"\nMerging video and audio into: {merging_filename}...", end='\r')
        sys.stdout.flush()
    else:
        print(f"\nDownload status: {progress.status}")
        # Print raw hook data for unknown statuses for debugging
        if progress._hook_data:
             print(f"Raw hook data: {progress._hook_data}")


# --- Example Usage ---
if __name__ == "__main__":
    # Replace with the URL of the video you want to download
    # Using the URL from your output for demonstration
    video_url = "https://www.youtube.com/watch?v=7ZFh7qI1xyg"

    # Create a downloader instance
    downloader = create_downloader("./my_downloads") # Downloads will be saved in ./my_downloads

    # Set the progress callback
    downloader.set_progress_callback(my_progress_callback)

    try:
        # 1. Validate the URL
        print(f"Validating URL: {video_url}")
        if not downloader.validate_url(video_url):
            print("Invalid or unsupported URL.")
            sys.exit(1)
        print("URL is valid.")

        # 2. Offer download options
        print("\nChoose a download option:")
        print("1. List all available formats and download by ID")
        print("2. Download best quality video with best audio (merged)")

        choice = input("Enter your choice (1 or 2): ").strip()

        if choice == '1':
            # List formats and download by ID
            print("\nFetching video information and available formats...")
            video_info: VideoInfo = downloader.get_video_info(video_url)

            print(f"\nVideo Title: {video_info.title}")
            print(f"Uploader: {video_info.uploader}")
            # Handle potential None for duration
            duration_display = f"{video_info.duration} seconds" if video_info.duration is not None else 'N/A'
            print(f"Duration: {duration_display}")
            print(f"Thumbnail: {video_info.thumbnail}")

            print("\nAvailable Formats:")
            if not video_info.formats:
                print("No downloadable formats found.")
            else:
                # Print available formats with their details
                print("-" * 120) # Increased width for more details
                print(f"{'ID':<10} | {'Ext':<5} | {'Resolution':<15} | {'Codec (v/a)':<15} | {'FPS':<5} | {'Filesize (approx)':<18} | {'Protocol':<10} | {'DR':<5} | {'Note'}")
                print("-" * 120)
                for fmt in video_info.formats:
                     # Get filesize in bytes, using approx if exact is not available
                     filesize_bytes = fmt.get('filesize') or fmt.get('filesize_approx')
                     filesize_display = "Unknown"
                     if filesize_bytes is not None and filesize_bytes > 0:
                         filesize_mb = filesize_bytes / (1024 * 1024) # Convert bytes to MB
                         filesize_display = f"{filesize_mb:.2f} MB"

                     # Explicitly convert values to string before formatting to handle potential None
                     format_id_display = str(fmt.get('format_id', 'N/A'))
                     ext_display = str(fmt.get('ext', 'N/A'))
                     resolution_display = str(fmt.get('resolution', 'N/A'))
                     vcodec_display = str(fmt.get('vcodec', 'N/A'))
                     acodec_display = str(fmt.get('acodec', 'N/A'))
                     # Handle FPS separately as it might be None and needs specific check
                     fps_value = fmt.get('fps')
                     fps_display = str(fps_value) if fps_value is not None else 'N/A'
                     note_display = str(fmt.get('format_note', 'N/A'))
                     protocol_display = str(fmt.get('protocol', 'N/A'))
                     dr_display = str(fmt.get('dynamic_range', 'N/A'))


                     print(
                         f"{format_id_display:<10} | "
                         f"{ext_display:<5} | "
                         f"{resolution_display:<15} | "
                         f"{vcodec_display}/{acodec_display:<15} | " # Increased width
                         f"{fps_display:<5} | "
                         f"{filesize_display:<18} | "
                         f"{protocol_display:<10} | "
                         f"{dr_display:<5} | "
                         f"{note_display}"
                     )
                print("-" * 120)

                # Prompt user for format selection
                selected_format_id = input("\nEnter the Format ID you want to download: ").strip()

                # Download the video with the selected format ID
                print(f"\nAttempting to download using format ID: {selected_format_id}")
                downloaded_file = downloader.download_video_by_format_id(video_url, selected_format_id)

                print(f"\nSuccessfully downloaded to: {downloaded_file}")

        elif choice == '2':
            # Download best quality video with best audio (merged)
            print("\nAttempting to download best quality video with best audio (merged)...")
            downloaded_file = downloader.download_best_quality_with_audio(video_url)

            print(f"\nSuccessfully downloaded and merged to: {downloaded_file}")

        else:
            print("Invalid choice. Please enter 1 or 2.")


    except RuntimeError as re:
        # Catch specific RuntimeError for FFmpeg not found
        print(f"\nError: {re}")
        print("Please ensure FFmpeg is installed and accessible in your system's PATH.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

