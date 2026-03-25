"""
Utility functions for voice agent pipline.

This module provides helper functions for working with async iterators, and other common operations across the pipeline.
"""

import asyncio
from typing import Any, AsyncIterator, TypeVar

T = TypeVar("T")

async def merge_async_iters(*aiters: AsyncIterator[T]) -> AsyncIterator[T]:
    """
    Merge multiple async iterators into a single async iterator.

    This function takes any number of async iterators and yields items from all
    of them as they become available, in the order they are produced. This is
    useful for combining multiple event streams (e.g., STT chunks, agent chunks,
    TTS chunks) into a single unified stream for processing.

    The function uses a queue-based approach with producer tasks for each input
    iterator. All iterators are consumed concurrently, and items are yielded as
    soon as any iterator produces them. The merged iterator completes only after
    all input iterators have been exhausted.

    Args:
        *aiters: Variable number of async iterators to merge.

    Yields:
        Items from any of the input iterators, in the order they become available.
    """
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    async def producer(aiter: AsyncIterator[Any]) -> None:
        async for item in aiter:
            await queue.put(item)
        await queue.put(sentinel)

    async with asyncio.TaskGroup() as tg:
        for a in aiters:
            tg.create_task(producer(a))

        finished = 0
        while finished < len(aiters):
            item = await queue.get()
            if item is sentinel:
                finished += 1
            else:
                yield item