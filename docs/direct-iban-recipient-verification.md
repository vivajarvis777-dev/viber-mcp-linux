# Direct IBAN recipient verification

Optional send_message verify_recipient=true requires exact active chat number through native Copy number, before composer input and again immediately before dispatch. It restores supported clipboard state, preserves the composer and runs inside the existing global UI mutex. No cached target/header-difference shortcut authorizes sending. Ordinary callers retain existing default behavior.

The X11 session uses actual X input focus rather than absent EWMH active-window metadata. Viber owner/PID, foreground focus, geometry and clipboard guards remain mandatory. Native Copy number action is located semantically; unsupported/ambiguous menus or wrong numbers block sending. Successful responses persist recipient_verified=true alongside text readback evidence.

Focused tests: 10 pass. Full suite: 213 passed before the final two send-gate cases; those cases subsequently passed. Live no-send inspection matched the existing open chat with the prior control order recipient and left the pre-existing composer unchanged. No draft insertion, clearing, paste-to-composer or send occurred. No service was restarted. Deployment requires VIBER_ALLOW_GUI=1 and VIBER_ALLOW_INPUT=1 in the existing MCP user service and owner-approved restart; desktop/session stays unchanged.

Apply the narrow patch from the vivagas-iban-viber repository to deployed source; do not overwrite unrelated changes from newer origin. Patch applicability was checked against the live baseline. See that repository for cutover/rollback and live acceptance gates.
