import time
import asyncio
import datetime
from threading import Lock, Event, Thread
from collections import deque
from typing import Deque
from ...video_types import Image
from ..video.frame_reader import FrameReader


class VideoBuffer:
    def __init__(self, temporal_capacity: datetime.timedelta, fps: int):
        self._frames: int = int(temporal_capacity.total_seconds()) * fps
        self.fps = fps
        self.video: Deque[Image] = deque(maxlen=self._frames)
        self._lock = Lock()

    def __len__(self):
        with self._lock:
            return len(self.video)
    
    def update(self, frame: Image):
        # assert frame is not None
        with self._lock:
            self.video.append(frame)

    def get_all(self) -> list[Image]:
        with self._lock:
            return list(self.video)


class VideoBufferManager:
    def __init__(self, video_buff: VideoBuffer, frame_source: FrameReader):
        self.video_buff = video_buff
        self.frame_source = frame_source
        self.period = 1 / video_buff.fps
        self._stop_event = Event()  # Use threading.Event
        self._thread: Thread | None = None

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()  # Wait for thread termination

    def _run(self):
        """Thread target function for frame reading"""
        next_frame_time = time.perf_counter()
        while not self._stop_event.is_set():
            # Read frame (blocking call is safe in dedicated thread)
            img = self.frame_source.read()
            self.video_buff.update(img)
            
            # Calculate sleep time for consistent FPS
            next_frame_time += self.period
            sleep_duration = max(0, next_frame_time - time.perf_counter())
            if sleep_duration > 0:
                time.sleep(sleep_duration)  # Non-busy wait

    def run_background(self):
        """Start frame reading in a dedicated thread"""
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            daemon=True  # Thread won't prevent program exit
        )
        self._thread.start()
        print("Started VideoBufferManager in background thread")