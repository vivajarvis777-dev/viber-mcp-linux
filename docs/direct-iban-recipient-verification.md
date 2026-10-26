# Direct IBAN recipient verification

Optional send_message verify_recipient=true requires exact active chat number through native Copy number, before composer input and again immediately before dispatch. It restores supported clipboard state, preserves the composer and runs inside the existing global UI mutex. No cached target/header-difference shortcut authorizes sending. Ordinary callers retain existing default behavior.

The X11 session uses actual X input focus rather than absent EWMH active-window metadata. Viber owner/PID, foreground focus, geometry and clipboard guards remain mandatory. Native Copy number action is located semantically; unsupported/ambiguous menus or wrong numbers block sending. Successful responses persist recipient_verified=true alongside text readback evidence.

Focused tests: 10 pass. Full suite: 215 passed, including both native send-gate cases. Live no-send inspection matched the existing open chat with the prior control order recipient and left the pre-existing composer unchanged. No draft insertion, clearing, paste-to-composer or send occurred. No service was restarted. Deployment requires VIBER_ALLOW_GUI=1 and VIBER_ALLOW_INPUT=1 in the existing MCP user service and owner-approved restart; desktop/session stays unchanged.

Apply the narrow patch from the vivagas-iban-viber repository to deployed source; do not overwrite unrelated changes from newer origin. Patch applicability was checked against the live baseline. See that repository for cutover/rollback and live acceptance gates.


## Verified navigation repair

Verified sends now establish the current native phone before consulting cached
navigation state. A native number match is authoritative even when a private
header pixel reference is stale. If the native number differs, UI search and
then URI navigation each require a fresh exact native number match. Neither a
changed header nor the cached target authorizes drafting. Clipboard, focus,
geometry, menu ambiguity and composer errors still stop the operation. All
navigation remains inside the existing global mutex and before the send claim.
The second identity check immediately before dispatch is unchanged.

This does not retry messages or reset terminal queue/approval records. A missing
composer or unverified native identity remains held for operator review. Callers
without verify_recipient keep their existing behavior.

Validation: 229 Python tests pass, including stale reference, stale cache,
wrong search result, both navigation paths wrong, UI guard failures and a
recipient change between draft and dispatch. Isolated tests send no messages.
