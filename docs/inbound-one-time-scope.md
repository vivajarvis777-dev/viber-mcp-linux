# Incoming Viber one-time reply — isolated candidate

Status: offline-only. Do not deploy, enable or send from this branch.

## Owner's scope

Reply once to a new incoming message from any Viber correspondent. Prior IBAN delivery, order, payment or outbound notification is **not** a prerequisite. Keep the recipient/chat identity guard: an incoming desktop notification alone must not authorize sending to a guessed person. No AI dialogue. The final message text and recipient for a live canary require separate owner approval.

## Changes in this candidate

- The old optional IBAN-history gate no longer restricts the recipient.
- Automatic reply limit is one per sender even if a stale environment setting asks for five or cooldown is zero. Explicit operator reset remains a manual exception.
- Desktop notification title must be a literal phone or an exact, unique saved contact/alias. Partial-name matching and arbitrary free text containing digits cannot authorize a recipient.
- No production code, workflow, service, ledger or Viber UI is modified by this branch.

## Open gates

- This branch retains the legacy direct Python sender. The owner wants a separate n8n workflow, so this is only a business-rule and identity regression candidate, **not** the target architecture.
- The experimental direct-send listener was stopped with owner approval (see below). The live MCP service remains active, but it does not run this isolated candidate; do not enable the old listener as a shortcut.
- A controlled real inbound Viber notification was observed **only after Viber lost focus** and XFCE notifications were active. The D-Bus sender PID belonged to the live Viber process, and the title/body were present; the title was **not a literal phone number**. The first two owner messages yielded no Viber notification while the app was focused. This proves an event in one UI state, not complete coverage or safe arbitrary-correspondent identity. No raw notification content was logged by the probe.
- There is still no proven safe route from that non-phone notification title to an exact personal chat for arbitrary unsaved correspondents. Do not enable automatic replies from this observation alone.
- Owning `org.freedesktop.Notifications` replaces the desktop notification service rather than transparently observing it. Audit notification UI impact and provenance before any activation.
- The legacy webhook forwarder is fire-and-forget and includes raw incoming text. It is not an accepted authenticated event queue for n8n; replace it before integration.
- The legacy implementation logs private notification text and may resend after a crash between UI send and ledger write. Treat both as blockers.
- The owner supplied a single customer-facing phone number and asked that the reply show only the number, without a person's name. The exact complete reply still needs owner approval before any send; no other phone is assumed.

## Owner-approved experimental listener shutdown

The owner explicitly approved stopping only experimental PID `750828`. The process and its wrapper were absent on readback; the production Viber MCP HTTP and Desktop user services remained active. The session bus notification name was initially unowned but activatable. With a separately owner-approved local notification, XFCE notifyd activated and remained active. For the third controlled inbound test the Viber window was temporarily unfocused, then its prior focus was restored and verified; Viber MCP, Viber Desktop and XFCE notifyd all remained active. No customer message was sent by the agent as part of these checks. Whether the experimental listener sent any earlier automatic reply remains unverified because its ad-hoc stdout log did not establish delivery.

## Acceptance before rollout

Demonstrate one controlled genuine inbound event in a safe no-send configuration; independently establish direction, personal-chat identity and recipient. `scripts/probe_incoming_notifications.py` is a bounded, read-only D-Bus monitor for the first observation: run it with system `/usr/bin/python3` (which has `dbus` and `gi`), on the existing session bus, and never print/store raw notification arguments. A private Python venv may lack these bindings. The probe reports only title shape and Viber-process provenance; it cannot prove exact sender identity or inbound message direction by itself. Prepare a separate inactive n8n workflow, minimal authenticated durable event intake, one-time idempotency, exact MCP recipient verification, unknown-send hold, sanitized logging, tests and rollback. Obtain explicit approval for the filled message, control recipient, production change and service/process cutover. Never run legacy sender concurrently with the new n8n route.
