"""Explicit real stdio acceptance; no mocks, credentials or broker actions."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(output: Path, configured: bool, minimal: bool) -> None:
    command, arguments = sys.executable, ['-m', 'meridian.mcp_server']
    environment = dict(os.environ)
    if configured:
        config = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
        settings = tomllib.loads(config.read_text(encoding='utf-8'))['mcp_servers']['meridian-alpha']
        command, arguments = settings['command'], settings.get('args', [])
        # Explicit public runtime configuration only; no credentials are read.
        for key in ('MERIDIAN_HOME', 'MERIDIAN_CACHE', 'MERIDIAN_POLICY_DIR'):
            if key in settings.get('env', {}):
                environment[key] = settings['env'][key]
    result = {'command': command, 'args': arguments, 'configured_host': configured,
              'started_at': datetime.now(UTC).isoformat(), 'calls': {}, 'execution_authority': 'NONE'}
    parameters = StdioServerParameters(command=command, args=arguments, env=environment)
    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
        initialized = await session.initialize()
        result['protocol_version'] = initialized.protocolVersion
        tools = (await session.list_tools()).tools
        result['tools'] = [tool.name for tool in tools]
        result['read_only'] = all(tool.annotations and tool.annotations.readOnlyHint for tool in tools)
        result['structured_schemas'] = all(tool.outputSchema for tool in tools)
        assert result['read_only'] and result['structured_schemas']
        assert not any(token in tool.name for tool in tools for token in ('submit', 'cancel_order', 'broker_login'))
        calls = [('runtime_status', {})]
        if not minimal:
            cutoff = datetime.now(UTC).isoformat()
            calls.extend([('market_snapshot', {'symbols': ['GOOGL'], 'analysis_cutoff': cutoff}),
                          ('company_facts', {'symbol': 'GOOGL', 'analysis_cutoff': cutoff}),
                          ('quant_metrics', {'symbol': 'GOOGL', 'bars': [], 'analysis_cutoff': cutoff}),
                          ('research_packet', {'symbol': 'GOOGL', 'analysis_cutoff': cutoff})])
        for name, args in calls:
            response = await session.call_tool(name, args)
            payload = response.structuredContent
            if payload is None:
                payload = json.loads(next(item.text for item in response.content if item.type == 'text'))
            result['calls'][name] = {'is_error': response.isError, 'payload': payload}
            assert not response.isError, name
            assert payload.get('execution_authority') == 'NONE', name
            print(name + ': ' + str(payload.get('status', payload.get('data_quality'))), flush=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['transport_status'] = 'PASS'
    result['completed_at'] = datetime.now(UTC).isoformat()
    result['result_hash'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--configured', action='store_true')
    parser.add_argument('--minimal', action='store_true')
    args = parser.parse_args()
    asyncio.run(run(args.output, args.configured, args.minimal))
