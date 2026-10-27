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
- The current experimental listener is a separate running process with both auto-reply and send enabled; it claims `org.freedesktop.Notifications`. Do not infer these isolated changes have reached it.
- There is no proven real Viber notification containing a reliable phone for arbitrary unsaved correspondents, including while the chat is open. Without this evidence, not every sender can be served automatically.
- Owning `org.freedesktop.Notifications` replaces the desktop notification service rather than transparently observing it. Audit notification UI impact and provenance before any activation.
- The legacy webhook forwarder is fire-and-forget and includes raw incoming text. It is not an accepted authenticated event queue for n8n; replace it before integration.
- The legacy implementation logs private notification text and may resend after a crash between UI send and ledger write. Treat both as blockers.
- No complete final reply including both confirmed business contact numbers has been approved, and no controlled recipient/message canary has been authorized.

## Acceptance before rollout

Demonstrate one controlled genuine inbound event in a safe no-send configuration; independently establish direction, personal-chat identity and recipient. Prepare a separate inactive n8n workflow, minimal authenticated durable event intake, one-time idempotency, exact MCP recipient verification, unknown-send hold, sanitized logging, tests and rollback. Obtain explicit approval for the filled message, control recipient, production change and service/process cutover. Never run legacy sender concurrently with the new n8n route.
