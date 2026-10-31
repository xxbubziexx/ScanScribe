"""Audio file metadata extraction utilities."""
import logging
from typing import Any, Dict, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from mutagen import File as MutagenFile
    from mutagen import MutagenError
    MUTAGEN_AVAILABLE = True
except ImportError:
    MutagenFile = None
    MutagenError = Exception
    MUTAGEN_AVAILABLE = False
    logger.warning("Mutagen not available - metadata extraction disabled")


def extract_audio_metadata(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Extract metadata from audio file.
    
    Args:
        file_path: Path to audio file (string or Path object)
    
    Returns:
        dict: Metadata including title, duration, artist, etc.
    """
    metadata = {
        "title": None,
        "artist": None,
        "album": None,
        "duration": 0.0,
        "bitrate": 0,
        "sample_rate": 0,
        "channels": 0
    }
    
    if not MUTAGEN_AVAILABLE:
        return metadata
    
    try:
        # Ensure file_path is a string for mutagen
        if isinstance(file_path, Path):
            file_path = str(file_path)
        
        audio = MutagenFile(file_path)
        
        if audio is None:
            logger.warning(f"Could not read metadata from {Path(file_path).name}")
            return metadata
        
        # Extract duration
        if hasattr(audio.info, 'length'):
            metadata["duration"] = audio.info.length
        
        # Extract bitrate
        if hasattr(audio.info, 'bitrate'):
            metadata["bitrate"] = audio.info.bitrate
        
        # Extract sample rate
        if hasattr(audio.info, 'sample_rate'):
            metadata["sample_rate"] = audio.info.sample_rate
        
        # Extract channels
        if hasattr(audio.info, 'channels'):
            metadata["channels"] = audio.info.channels
        
        # Extract tags (title, artist, album)
        if audio.tags:
            # Try different tag formats (ID3, Vorbis, etc.)
            title_keys = ['TIT2', 'title', 'TITLE', '©nam']
            artist_keys = ['TPE1', 'artist', 'ARTIST', '©ART']
            album_keys = ['TALB', 'album', 'ALBUM', '©alb']
            
            for key in title_keys:
                if key in audio.tags:
                    value = audio.tags[key]
                    metadata["title"] = str(value[0]) if isinstance(value, list) else str(value)
                    break
            
            for key in artist_keys:
                if key in audio.tags:
                    value = audio.tags[key]
                    metadata["artist"] = str(value[0]) if isinstance(value, list) else str(value)
                    break
            
            for key in album_keys:
                if key in audio.tags:
                    value = audio.tags[key]
                    metadata["album"] = str(value[0]) if isinstance(value, list) else str(value)
                    break
        
        logger.debug(f"Extracted metadata from {Path(file_path).name}: title={metadata['title']}, duration={metadata['duration']:.2f}s")
        
    except MutagenError as e:
        # Mutagen refuses files that are incomplete or malformed - normally a
        # capture read while it was still being written. Not a reason to alarm:
        # the audio still decodes for transcription, and the talkgroup falls
        # back to the filename (see get_talkgroup_from_metadata).
        logger.warning(
            f"Could not parse audio metadata from {Path(file_path).name}: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error extracting metadata from {Path(file_path).name}: {str(e)}")
    
    return metadata


def get_talkgroup_from_metadata(metadata: Dict[str, Any], filename: Optional[str] = None) -> str:
    """
    Extract talkgroup/channel info from an audio metadata dict.

    Prefers the ID3 title. When mutagen could not parse the file, the channel
    must not be lost: recorders encode it in the filename, so fall back to that
    instead of reporting "N/A".

    Args:
        metadata: Metadata dictionary from extract_audio_metadata()
        filename: Optional source filename, used as the fallback

    Returns:
        str: Talkgroup name or "N/A" if it cannot be determined
    """
    if metadata and metadata.get("title"):
        # The title field usually contains talkgroup info in scanner recordings
        return metadata["title"]

    derived = _talkgroup_from_filename(filename) if filename else None
    if derived:
        return derived

    return "N/A"


def _talkgroup_from_filename(filename: str) -> Optional[str]:
    """
    Derive a channel name from a recorder filename.

    Handles the common ProScan shape
    "<timestamp>_<system> - <channel>.mp3" -> "<channel>", degrading to the
    post-timestamp segment when there is no " - " separator.
    """
    if not filename:
        return None

    stem = Path(filename).stem.strip()
    if not stem:
        return None

    if "_" in stem:
        stem = stem.split("_", 1)[1].strip()

    if " - " in stem:
        stem = stem.rsplit(" - ", 1)[1].strip()

    return stem or None


def get_audio_duration(file_path: Path) -> float:
    """
    Get audio file duration in seconds.
    
    Returns:
        float: Duration in seconds, or 0.0 if unable to determine
    """
    metadata = extract_audio_metadata(file_path)
    return metadata["duration"]
