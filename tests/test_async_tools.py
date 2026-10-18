import asyncio
import threading
import time
import linux_server


def test_slow_ui_does_not_block_event_loop():
    async def scenario():
        entered = threading.Event()
        release = threading.Event()
        def slow():
            entered.set()
            release.wait(2)
            return 'done'
        task = asyncio.create_task(linux_server.invoke(slow))
        try:
            deadline = time.monotonic() + 1
            while not entered.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert entered.is_set()
            assert not task.done(), 'sync tool blocked the event loop'
        finally:
            release.set()
        assert await task == 'done'
    asyncio.run(scenario())


def test_cancellation_stops_worker(monkeypatch):
    stopped = threading.Event()
    monkeypatch.setattr(linux_server.service, 'stop', stopped.set)
    async def scenario():
        task = asyncio.create_task(linux_server.invoke(lambda: stopped.wait(2)))
        await asyncio.sleep(.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert stopped.is_set()
    asyncio.run(scenario())
