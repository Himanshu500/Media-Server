import os
import re
import mimetypes
import logging
from flask import Flask, Response, render_template, request, jsonify, abort
from typing import List, Dict, Optional, Tuple, Any
import cv2 # For video metadata
import utils # Assuming utils.py contains get_primary_ip_address

# --- Globals ---
app = Flask(__name__, template_folder='templates')
logger = logging.getLogger(__name__)

# To store the list of available video files
# Each item will be a dictionary: {'filename': str, 'path': str}
AVAILABLE_VIDEOS: List[Dict[str, str]] = []
# To cache metadata for videos to avoid re-reading
VIDEO_METADATA_CACHE: Dict[str, Dict[str, Any]] = {}


# --- Server State Initialization ---
def init_server_state(video_files: List[Dict[str, str]]) -> None:
    """
    Initializes the server state with the list of available video files.
    Pre-caches metadata for all videos.
    """
    global AVAILABLE_VIDEOS, VIDEO_METADATA_CACHE
    AVAILABLE_VIDEOS = video_files
    VIDEO_METADATA_CACHE = {} # Clear previous cache

    if not AVAILABLE_VIDEOS:
        logger.warning("Server initialized with no video files.")
    else:
        logger.info(f"Server initialized with {len(AVAILABLE_VIDEOS)} video files.")
        # Pre-cache metadata for all videos
        for video_data in AVAILABLE_VIDEOS:
            try:
                metadata = get_video_info(video_data['path'])
                if metadata:
                    VIDEO_METADATA_CACHE[video_data['filename']] = metadata
                    logger.debug(f"Cached metadata for {video_data['filename']}")
                else:
                    logger.warning(f"Could not get metadata for {video_data['path']}")
            except Exception as e:
                logger.error(f"Error caching metadata for {video_data['path']}: {e}")

def get_video_by_filename(filename: str) -> Optional[Dict[str, str]]:
    """Finds a video in AVAILABLE_VIDEOS by its filename."""
    for video in AVAILABLE_VIDEOS:
        if video['filename'] == filename:
            return video
    return None

# --- Video Metadata ---
def get_video_info(video_path: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves video metadata (resolution, duration, FPS) for a given video file path.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found at path: {video_path}")
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Could not open video file: {video_path}")
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()

        # Guess mime type
        mime_type, _ = mimetypes.guess_type(video_path)
        if not mime_type:
             # Fallback if mime type can't be guessed based on extension
            if video_path.lower().endswith(('.mp4', '.m4v')):
                mime_type = 'video/mp4'
            elif video_path.lower().endswith('.mkv'):
                mime_type = 'video/x-matroska' # Common, though not always standard
            elif video_path.lower().endswith('.webm'):
                mime_type = 'video/webm'
            elif video_path.lower().endswith('.mov'):
                mime_type = 'video/quicktime'
            else:
                mime_type = 'application/octet-stream' # Generic fallback

        info = {
            "filename": os.path.basename(video_path),
            "path": video_path,
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "frame_count": frame_count,
            "mime_type": mime_type
        }
        logger.info(f"Retrieved video info for {video_path}: W={width}, H={height}, Dur={duration:.2f}s, FPS={fps:.2f}, Mime={mime_type}")
        return info
    except Exception as e:
        logger.error(f"Error getting video info for {video_path} using OpenCV: {e}")
        return None

# --- HTTP Byte-Range Streaming Logic ---
def send_video_range_request(video_path: str, range_header: Optional[str]) -> Response:
    """
    Handles serving a video file with support for HTTP byte range requests.
    Takes the full path to the video file.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found for streaming: {video_path}")
        return Response("Video file not found.", status=404)

    file_size = os.path.getsize(video_path)
    _, mime_type = mimetypes.guess_type(video_path)
    if mime_type is None: # Fallback for unknown types
        mime_type = 'application/octet-stream'
        logger.warning(f"Could not guess MIME type for {video_path}, using {mime_type}")

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Accept-Ranges': 'bytes'
    }

    if range_header:
        range_match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start_byte = int(range_match.group(1))
            end_byte_str = range_match.group(2)
            
            if end_byte_str:
                end_byte = int(end_byte_str)
            else:
                # If no end byte, serve a chunk (e.g., 1MB or 2MB) or to the end of file if small
                # For robust streaming, clients usually specify the end or request small chunks
                # Let's define a sensible chunk size, or go to end if it's the last part.
                # Many players request specific small ranges or up to end of file.
                end_byte = file_size - 1 # Default to serving till the end of the file

            # Ensure range is valid
            if start_byte >= file_size or end_byte >= file_size or start_byte > end_byte:
                logger.warning(f"Invalid range request: {range_header} for file size {file_size}")
                return Response("Requested Range Not Satisfiable", status=416, headers={'Content-Range': f'bytes */{file_size}'})

            length = end_byte - start_byte + 1
            headers['Content-Length'] = str(length)
            headers['Content-Range'] = f'bytes {start_byte}-{end_byte}/{file_size}'
            
            status_code = 206 # Partial Content

            def generate_chunks():
                with open(video_path, 'rb') as f:
                    f.seek(start_byte)
                    bytes_to_send = length
                    while bytes_to_send > 0:
                        chunk_size = min(bytes_to_send, 65536) # 64KB chunks
                        data_chunk = f.read(chunk_size)
                        if not data_chunk:
                            break
                        yield data_chunk
                        bytes_to_send -= len(data_chunk)
            
            logger.info(f"Serving range: {start_byte}-{end_byte} for {os.path.basename(video_path)}")
            return Response(generate_chunks(), status=status_code, headers=headers)
        else:
            logger.warning(f"Malformed Range header: {range_header}")
            # Fall through to serving the full file if range is malformed, or return error
            # For simplicity, let's serve full file if range parsing fails but header exists
            pass # This will lead to serving the full file below

    # If no range_header or malformed, serve the full file
    logger.info(f"Serving full file: {os.path.basename(video_path)}")
    def generate_full_file():
        with open(video_path, 'rb') as f:
            while True:
                data_chunk = f.read(65536) # 64KB chunks
                if not data_chunk:
                    break
                yield data_chunk
    return Response(generate_full_file(), status=200, headers=headers)


# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML page with the video gallery."""
    if not AVAILABLE_VIDEOS:
        logger.warning("Index route called but no videos available.")
        # Create a simple message or render a 'no_video_loaded_yet.html' if you want
        # For now, let's pass an empty list to index.html, which should handle it.
        return render_template('no_video.html', message="No video directory has been loaded by the server.")

    # Prepare a list of video filenames for the template
    # The template will use these filenames to construct stream and info URLs
    video_filenames_for_template = [v['filename'] for v in AVAILABLE_VIDEOS]
    
    logger.info(f"Serving index page with {len(video_filenames_for_template)} videos.")
    
    # Get primary IP for constructing full URLs if needed by template (e.g. for QR code in future)
    # For now, template will use relative URLs for /stream and /api/video_info
    server_ip = utils.get_local_ip() # Changed from get_primary_ip_address

    return render_template(
        'index.html',
        videos=video_filenames_for_template,
        server_ip=server_ip # Pass server IP if template needs it for full URLs
    )

@app.route('/stream/<path:video_filename>')
def stream_video(video_filename: str):
    """Streams the specified video file with byte-range support."""
    logger.info(f"Received stream request for: {video_filename}")
    
    video_data = get_video_by_filename(video_filename)
    if not video_data:
        logger.error(f"Video '{video_filename}' not found in available videos.")
        abort(404, description="Video not found")
        
    video_path = video_data['path']
    range_header = request.headers.get('Range', None)
    
    return send_video_range_request(video_path, range_header)

@app.route('/api/video_info/<path:video_filename>')
def api_video_info(video_filename: str):
    """Returns metadata for the specified video file as JSON."""
    logger.info(f"Received API video info request for: {video_filename}")

    # Check if metadata is already cached
    if video_filename in VIDEO_METADATA_CACHE:
        logger.debug(f"Returning cached metadata for {video_filename}")
        return jsonify(VIDEO_METADATA_CACHE[video_filename])

    # If not cached (should have been by init_server_state, but as a fallback)
    video_data = get_video_by_filename(video_filename)
    if not video_data:
        logger.error(f"Video '{video_filename}' not found for info request.")
        abort(404, description="Video not found")

    metadata = get_video_info(video_data['path'])
    if metadata:
        VIDEO_METADATA_CACHE[video_filename] = metadata # Cache it now
        return jsonify(metadata)
    else:
        logger.error(f"Could not retrieve metadata for {video_filename} at {video_data['path']}")
        abort(500, description="Could not retrieve video metadata")


# --- Old single video related code - To be removed or commented out ---
# VIDEO_FILE_PATH: Optional[str] = None
# video_info_cache: Dict[str, Any] = {}

# def set_video_path(filepath: str) -> Optional[Dict[str, Any]]:
#     global VIDEO_FILE_PATH, video_info_cache
#     if not os.path.exists(filepath) or not os.path.isfile(filepath):
#         logger.error(f"Video file does not exist or is not a file: {filepath}")
#         VIDEO_FILE_PATH = None
#         video_info_cache = {}
#         return None
#     VIDEO_FILE_PATH = filepath
#     logger.info(f"Video file set to: {VIDEO_FILE_PATH}")
#     video_info_cache = get_video_info(VIDEO_FILE_PATH) # Update cache
#     return video_info_cache

# @app.route('/video_stream') # This will be replaced by /stream/<filename>
# def video_stream_deprecated():
#     if not VIDEO_FILE_PATH:
#         logger.error("Video stream request but no video file path is set.")
#         abort(404, description="No video file loaded")
#     range_header = request.headers.get('Range', None)
#     return send_video_range_request(VIDEO_FILE_PATH, range_header)

# --- Main (for direct execution, though usually run via cli.py) ---
if __name__ == '__main__':
    # This is for direct testing of server.py.
    # In normal operation, cli.py will configure and run the app.
    logging.basicConfig(level=logging.DEBUG)
    logger.info("Starting server directly for testing (without cli.py)...")
    
    # Create some dummy video data for testing
    # In a real scenario, cli.py provides this.
    # You'd need to create dummy video files (e.g., test1.mp4, test2.mkv) in a 'test_videos' folder.
    test_video_dir = "test_videos_for_server_dev"
    os.makedirs(test_video_dir, exist_ok=True)
    # Create tiny dummy files for testing structure - these won't play
    dummy_files_to_create = ["test1.mp4", "test2.mkv"]
    created_video_files_for_test = []
    for fname in dummy_files_to_create:
        fpath = os.path.join(test_video_dir, fname)
        if not os.path.exists(fpath): # Create if doesn't exist
            with open(fpath, 'w') as f:
                f.write("dummy content") # Actual video content not needed for this structural test
        created_video_files_for_test.append({"filename": fname, "path": os.path.abspath(fpath)})
    
    if not created_video_files_for_test:
         logger.warning(f"Could not create/find dummy videos in {test_video_dir} for testing.")
         logger.warning("Please create some files like 'test1.mp4', 'test2.mkv' in a subdirectory for server.py direct testing.")

    init_server_state(video_files=created_video_files_for_test)
    
    # A simple IP for testing if utils isn't fully set up or get_primary_ip_address fails
    try:
        server_ip_test = utils.get_primary_ip_address()
        if not server_ip_test: server_ip_test = "127.0.0.1"
    except AttributeError: # if utils or function missing
        logger.warning("utils.get_primary_ip_address not found, using 127.0.0.1 for test URLs.")
        server_ip_test = "127.0.0.1"

    port = 5005 # Use a different port for direct testing
    print(f"\n --- Server.py Direct Test Mode --- ")
    print(f"Open your browser to http://{server_ip_test}:{port}/")
    if AVAILABLE_VIDEOS:
        print("Available videos for testing:")
        for v_test in AVAILABLE_VIDEOS:
            print(f"  - {v_test['filename']}")
            print(f"    Stream: http://{server_ip_test}:{port}/stream/{v_test['filename']}")
            print(f"    Info:   http://{server_ip_test}:{port}/api/video_info/{v_test['filename']}")
    else:
        print("No test videos loaded. Index page may be empty or show an error.")
    print(" ---------------------------------- ")

    app.run(host='0.0.0.0', port=port, debug=True, threaded=True) 