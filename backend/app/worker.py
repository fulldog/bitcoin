"""Research worker entry point.

The first slice intentionally keeps job execution explicit. A later slice adds
durable Redis-backed jobs without making Redis the source of trading truth.
"""

import asyncio


async def main() -> None:
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
