"""Human-only approval ceremony; never exposed as an MCP tool."""
import argparse
import getpass
import os
import sys
from linux_domain import Service, phone


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipient', required=True, help='Exact phone literal or self:my-notes')
    args = p.parse_args()
    recipient = args.recipient if args.recipient == 'self:my-notes' else phone(args.recipient)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit('Approval requires an independent human terminal, not MCP or a pipe')
    print('Recipient (exact, no normalization):', recipient)
    print('Enter exact text as JSON string, including quotes and escaped newlines.')
    import json
    text = json.loads(getpass.getpass('Text JSON (hidden): '))
    Service.validate_text(text)
    print('Exact draft for human review:', repr(text))
    if input('Type APPROVE EXACT SEND to approve once for 5 minutes: ') != 'APPROVE EXACT SEND':
        raise SystemExit('Not approved')
    token = Service().store().approve(recipient, text)
    print('One-time token:', token)

if __name__ == '__main__': main()
