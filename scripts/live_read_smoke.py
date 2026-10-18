"""Explicit read-only MCP check. Prints counts/timing, never private OCR content."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(region, repeat):
    env = dict(os.environ, VIBER_ALLOW_INPUT='0', VIBER_ENABLE_SEND='0')
    params = StdioServerParameters(command=sys.executable,
                                  args=[str(Path(__file__).resolve().parents[1] / 'server.py')], env=env)
    durations, counts = [], []
    offline = False
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(repeat):
                start = time.monotonic()
                result = await session.call_tool('read_visible', {'region': region})
                if result.isError:
                    print(json.dumps({'live_read': False, 'tool_error': True}))
                    return 1
                data = result.structuredContent
                if not isinstance(data, dict):
                    data = json.loads(result.content[0].text)
                durations.append(round((time.monotonic() - start) * 1000))
                counts.append(data.get('line_count', 0))
                offline |= 'no internet connection' in data.get('text', '').casefold()
    print(json.dumps({'live_read': True, 'region': region, 'calls': repeat,
                      'lines_per_call': counts, 'latency_ms': durations,
                      'median_ms': statistics.median(durations), 'offline_observed': offline,
                      'input_enabled': False, 'send_enabled': False, 'private_text_printed': False}))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', choices=['status', 'sidebar', 'header', 'conversation'], default='status')
    parser.add_argument('--repeat', type=int, choices=range(1, 11), default=3)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(check(args.region, args.repeat)))
