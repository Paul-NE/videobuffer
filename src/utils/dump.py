from pathlib import Path
import asyncio
import datetime
import threading

import cv2
from ..buffer.video_buffer import VideoBuffer
from .approval import DumpApproval

def dump2file(video_buff: VideoBuffer, filename: Path, exist_ok: bool = False):
    if filename.exists() and not exist_ok:
        raise FileExistsError("File already exists.")

    frames = video_buff.get_all()
    if not frames:
        raise ValueError("Buffer is empty.")

    height, width, channels = frames[0].shape
    assert channels == 3

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(filename), fourcc, video_buff.fps, (width, height))

    for frame in frames:
        out.write(frame)

    out.release()
    print(f"Saved to {filename}")

def _delayed_save_worker(
    video_buff: VideoBuffer,
    filename: Path,
    approval: DumpApproval,
    delay: datetime.timedelta,
    exist_ok: bool = False
):
    import time
    time.sleep(delay.total_seconds())
    if approval.is_approved():  # Assuming is_approved() is synchronous now
        dump2file(video_buff, filename, exist_ok)
    else:
        print("Dump aborted — not approved.")

async def dump2file_delayed(
    video_buff: VideoBuffer,
    filename: Path,
    approval: DumpApproval,
    delay: datetime.timedelta,
    exist_ok: bool = False,
):
    await asyncio.sleep(delay.total_seconds())
    if await approval.is_approved():
        await asyncio.to_thread(dump2file, video_buff, filename, exist_ok)
    else:
        print("Dump aborted — not approved.")

def save_delayed_init(video_buffer:VideoBuffer, save_dir:Path, delay:datetime.timedelta) -> tuple[asyncio.Task, DumpApproval]:
    approval = DumpApproval()
    current_time = datetime.datetime.now()
    time_str = current_time.strftime("%m_%d_%Y;%H_%M_%S")
    save_task = asyncio.create_task(dump2file_delayed(
        video_buff=video_buffer, 
        filename=save_dir / f"{time_str}.mp4", 
        approval=approval, 
        delay = delay, 
        exist_ok=False))
    return (save_task, approval)

def save_delayed_autoaprove(video_buffer:VideoBuffer, save_dir:Path, delay:datetime.timedelta) -> tuple[asyncio.Task, DumpApproval]:
    save_task, approval = save_delayed_init(video_buffer, save_dir, delay)
    approval.approve()
    return (save_task, approval)

def save_delayed_init_threaded(video_buffer:VideoBuffer, save_dir:Path, delay:datetime.timedelta) -> tuple[threading.Thread, DumpApproval]:
    approval = DumpApproval()
    current_time = datetime.datetime.now()
    time_str = current_time.strftime("%m_%d_%Y;%H_%M_%S")
    
    thread = threading.Thread(
        target=_delayed_save_worker,
        kwargs={
            'video_buff': video_buffer,
            'filename': save_dir / f"{time_str}.mp4",
            'approval': approval,
            'delay': delay,
            'exist_ok': False
        },
        daemon=True  # Daemon thread will exit when main program exits
    )
    thread.start()
    
    return (thread, approval)

def save_delayed_autoaprove_threaded(video_buffer:VideoBuffer, save_dir:Path, delay:datetime.timedelta) -> tuple[threading.Thread, DumpApproval]:
    thread, approval = save_delayed_init_threaded(video_buffer, save_dir, delay)
    approval.approve()
    return (thread, approval)
