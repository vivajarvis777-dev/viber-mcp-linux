"""Operator-approved, one-call draft acceptance gate. Never sends or retries.

Call after verifying the intended chat and empty composer. Pass the exact env
used for StdioServerParameters. A diagnostic preflight failure prevents the RPC.
This helper is not a new MCP tool or an approval issuer.
"""
import asyncio
import json
import os
from pathlib import Path

from linux_diagnostics import phase, record
from linux_domain import phone
from scripts.hermes_smoke import find_payload


def diagnostic_preflight(destination):
    if not destination:
        raise ValueError('diagnostic_preflight_failed')
    path = Path(destination)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError('diagnostic_preflight_failed')
    previous = os.environ.get('VIBER_DIAGNOSTICS_FILE')
    try:
        os.environ['VIBER_DIAGNOSTICS_FILE'] = str(path)
        with phase('setup'):
            written = record('diagnostic_probe', 'probe')
        if written is not True:
            raise ValueError('diagnostic_preflight_failed')
        event = json.loads(path.read_text())
        if event.get('command_kind') != 'diagnostic_probe' or event.get('failure_kind') != 'probe':
            raise ValueError('diagnostic_preflight_failed')
    except (OSError, ValueError):
        raise ValueError('diagnostic_preflight_failed') from None
    finally:
        if previous is None:
            os.environ.pop('VIBER_DIAGNOSTICS_FILE', None)
        else:
            os.environ['VIBER_DIAGNOSTICS_FILE'] = previous


async def checked_draft(session, text, env, *, expected_recipient, recipient_reader, draft_reader,
                        timeout=30):
    if not 0 < timeout <= 30:
        raise ValueError('invalid_acceptance_timeout')
    if (env.get('VIBER_ENABLE_SEND') != '0' or env.get('VIBER_ALLOW_INPUT') != '1'
            or env.get('VIBER_ALLOW_GUI') != '1'):
        raise ValueError('draft_only_environment_required')
    expected_recipient = phone(expected_recipient)
    diagnostic_preflight(env.get('VIBER_DIAGNOSTICS_FILE'))
    health = await asyncio.wait_for(session.call_tool('health', {}), timeout=min(timeout, 5))
    health_data = health.model_dump() if hasattr(health, 'model_dump') else health
    health_payload = find_payload(health_data, 'send_enabled', False)
    if (health_data.get('isError', False) or not health_payload
            or health_payload.get('send_enabled') is not False):
        raise ValueError('actual_session_send_disabled_required')
    if recipient_reader() != expected_recipient:
        raise ValueError('acceptance_recipient_mismatch')
    if draft_reader() != '':
        raise ValueError('acceptance_draft_not_empty')
    # No retry, fallback, navigation or cleanup RPC after an uncertain result.
    result = await asyncio.wait_for(session.call_tool('put_draft', {
        'text': text, 'expected_recipient': expected_recipient}), timeout=timeout)
    data = result.model_dump() if hasattr(result, 'model_dump') else result
    if not data.get('isError', False):
        payload = find_payload(data, 'drafted', True)
        if (not payload or payload.get('recipient') != expected_recipient
                or payload.get('verified') is not True or draft_reader() != text):
            raise ValueError('draft_result_unverified_no_retry')
    return result
