import asyncio
import functools
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor


async def run_blocking[T](executor: Executor, fn: Callable[..., T], *args: object) -> T:
    """Run a blocking call on ``executor`` without stalling the event loop."""
    return await asyncio.get_running_loop().run_in_executor(executor, functools.partial(fn, *args))


def threadsafe_progress(
    on_progress: Callable[[float], Awaitable[None]],
    loop: asyncio.AbstractEventLoop,
    min_step: float = 0.01,
) -> Callable[[float], None]:
    """Wrap an async progress callback so a worker thread can call it. Calls that move
    less than ``min_step`` since the last report are dropped, since blocking libraries
    report far more often than the UI needs."""
    last = -1.0

    def report(fraction: float) -> None:
        nonlocal last
        if fraction - last >= min_step or fraction >= 1.0 > last:
            last = fraction
            asyncio.run_coroutine_threadsafe(on_progress(fraction), loop)

    return report
