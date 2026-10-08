"""Read-only MCP check; prints counts and tool names, never filenames or tokens."""
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    here = Path(__file__).resolve().parent
    settings = json.loads((here / 'settings.json').read_text(encoding='utf-8-sig'))
    checks = [('local', sys.executable, str(here / 'start-local.py'))]
    if '--local-only' not in sys.argv:
        import shutil
        checks.insert(0, ('remote', shutil.which('node'), str(here / 'start-remote.mjs')))
    with open(os.devnull, 'w') as quiet:
        for name, command, script in checks:
            params = StdioServerParameters(command=command, args=[script])
            async with stdio_client(params, errlog=quiet) as (rd, wr):
                async with ClientSession(rd, wr) as client:
                    await client.initialize()
                    names = [tool.name for tool in (await client.list_tools()).tools]
                    output = {'connection': name, 'initialized': True, 'tools': names}
                    if name == 'remote':
                        result = await client.call_tool('file_list', {'dir': '/', 'page': 1})
                        data = json.loads(next(b.text for b in result.content if hasattr(b, 'text')))
                        output['rootListingErrno'] = data.get('errno')
                        if result.isError or data.get('errno') != 0: raise RuntimeError('Read failed')
                    print(json.dumps(output))


if __name__ == '__main__':
    try: asyncio.run(asyncio.wait_for(main(), 90))
    except Exception:
        print(json.dumps({'success': False, 'reason': 'MCP check failed. Check installation, authorization and network.'}))
        sys.exit(1)
