import asyncio

class DumpApproval:
    def __init__(self):
        self._approved = False
        self._lock = asyncio.Lock()

    async def approve(self):
        async with self._lock:
            self._approved = True

    async def reject(self):
        async with self._lock:
            self._approved = False

    async def is_approved(self) -> bool:
        async with self._lock:
            return self._approved
