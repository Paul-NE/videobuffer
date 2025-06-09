import threading
import av
import time
import cv2
from abc import ABC, abstractmethod
from typing import Optional
from ...video_types import Image

class FrameReader(ABC):
    @abstractmethod
    def read(self) -> Image:
        raise NotImplementedError
    @abstractmethod
    def stop(self):
        raise NotImplementedError


class VideoCycleFrameReader(FrameReader):
    def __init__(self, cap: cv2.VideoCapture, fps=20):
        self.cap = cap
        self.frame_interval = 1 / fps
        self._latest_frame: Optional[Image] = None
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._update_frame, daemon=True)
        self._thread.start()
        
    def _update_frame(self):
        while self._running:
            current_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
            frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if current_frame >= frame_count - 1:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._latest_frame = frame
            time.sleep(self.frame_interval)
    
    def read(self) -> Optional[Image]:
        with self._lock:
            ret = self._latest_frame.copy() if self._latest_frame is not None else None
            return ret 
    
    def stop(self):
        self._running = False
        self._thread.join()
        self.cap.release()


import logging

logging.basicConfig(level=logging.INFO)

class RTSPFrameReader(FrameReader):
    def __init__(self, rtsp_url, reconnect_delay=5, timeout=5):
        """
        :param rtsp_url: RTSP stream URL
        :param reconnect_delay: Reconnection delay in seconds (default: 5)
        :param timeout: Network timeout in seconds (default: 5)
        """
        self.rtsp_url = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.timeout = timeout * 1000000  # Convert to microseconds
        self.running = False
        self.thread = None
        
        # Thread-safe frame sharing
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.frame_available = threading.Event()
        
        # Reconnection stats
        self.connection_attempts = 0
        self.last_frame_time = 0

    def start(self):
        """Start the frame reading thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the frame reading thread"""
        if self.running:
            self.running = False
            self.thread.join(timeout=2.0)
            with self.frame_lock:
                self.latest_frame = None

    def _update(self):
        while self.running:
            try:
                # Configure FFmpeg for reliable RTSP
                options = {
                    'rtsp_transport': 'tcp',       # Force TCP transport
                    'stimeout': str(self.timeout),  # Network timeout
                    'max_delay': '500000',         # Max demux delay
                    'fflags': 'nobuffer',          # Reduce latency
                    'flags': 'low_delay',          # Low latency mode
                    'analyzeduration': '1000000',  # Faster analysis
                    'probesize': '4096'            # Smaller probe size
                }
                
                with av.open(self.rtsp_url, options=options) as container:
                    stream = container.streams.video[0]
                    stream.thread_type = 'AUTO'    # Automatic threading
                    
                    self.connection_attempts = 0
                    logging.info(f"Connected to {self.rtsp_url}")
                    
                    for frame in container.decode(stream):
                        if not self.running:
                            return
                            
                        # Convert to BGR numpy array
                        img = frame.to_ndarray(format='bgr24')
                        
                        # Update shared frame
                        with self.frame_lock:
                            self.latest_frame = img
                        self.frame_available.set()
                        self.last_frame_time = time.time()
                        
            except Exception as e:
                logging.error(f"Stream error: {str(e)}")
                self.connection_attempts += 1
                
                # Clear frame on disconnection
                with self.frame_lock:
                    self.latest_frame = None
                self.frame_available.clear()
                
                if self.running:
                    sleep_time = min(self.reconnect_delay * self.connection_attempts, 30)
                    logging.warning(f"Reconnecting in {sleep_time}s (attempt #{self.connection_attempts})...")
                    time.sleep(sleep_time)

    def read(self):
        """
        Get the latest frame with thread-safe access
        :return: Frame as numpy array (BGR format) or None if unavailable
        """
        # Wait for frame if none available
        if not self.frame_available.is_set():
            self.frame_available.wait(1.0)
            
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()  # Return copy to prevent race conditions

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
