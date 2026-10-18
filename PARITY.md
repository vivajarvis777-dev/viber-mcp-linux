# Повна матриця інструментів upstream

Джерело: `wawimundo/viber-mcp`, commit `af1d0ed1b880dc28a18f2d5198a4d09b52047bd4`, `server.py` (копія `upstream_server.py`). MCP names: **11/11**; додані `health`, `stop`. Це паритет поверхні API та реалізованих шляхів, **не доказ повного operational parity на живому Viber**.

| Точний upstream tool | Linux-реалізація | Перевірено | Навмисна safety-різниця / ще не перевірено |
|---|---|---|---|
| `send_message(to,text,dry_run=False)` | resolve literal/alias → exact search → identity → protected draft → approved action → new outgoing ID/readback | synthetic domain: dry_run, send, replay, Unicode; MCP disabled rejection; AT-SPI write/action на GTK | `approval_token` додатковий; send disabled default; жодного реального Viber send |
| `open_chat(to)` | exact search + contact-details phone verification | synthetic domain і AT-SPI exact navigation | не додає країну/`+`; фактичний Viber profile не відкалібрований |
| `open_and_read(to)` | та сама транзакція navigation + conversation-only read + повторна identity | synthetic domain; scoped AT-SPI read на GTK | не читає sidebar разом із розмовою; живий Viber не читався |
| `reply(text)` | current identity порівнюється з явним `to`; protected draft + approval send | synthetic domain, approval-required MCP rejection | додаткові `to`, `approval_token`; відкритий чат не є авторизацією |
| `search_and_open(name)` | unique exact accessible row; observed contact-details identity; conversation-only read | synthetic domain із alias і без; GTK exact result | prefix/substring «best guess» вилучено; без alias `recipient_verified:false`, ніколи автоматично не авторизує send |
| `list_chats()` | тільки `sidebar` subtree; visible labels/previews/times/unread як текст | synthetic domain; реальний scoped GTK read | як upstream — тільки видиме; реальні sidebar/labels не читалися |
| `put_draft(text)` | current exact identity; EditableText + Unicode readback; no click | synthetic domain; реальний GTK Cyrillic/emoji/newline readback | інший існуючий draft захищений; Qt/Viber EditableText ще не перевірено |
| `save_to_my_notes(text)` | explicit self recipient + independent self marker + approval | synthetic domain success + MCP send-disabled rejection | My Notes не можна визнати за самою назвою; жодних live self-note тестів, marker Viber не встановлений |
| `open_my_notes()` | exact My Notes search + independent self identity | synthetic domain success + MCP GUI-disabled rejection | реальна self-ідентичність Viber не перевірена |
| `read_open_chat()` | current identity + `conversation` scoped read + identity recheck | synthetic domain; реальний GTK scope test | AT-SPI замість OCR; жодних live private chat reads |
| `list_contacts()` | explicit private alias file, strict literal validation | synthetic JSON fixture; MCP empty map without file | файл не шукається у приватних чатах; literal зберігається, malformed не «виправляється» |

## Рівні доказів

1. **Unit/domain fixture:** усі 11 шляхів, включно з notes/send, працюють проти явно синтетичного backend; це не Viber.
2. **Справжній MCP stdio:** initialize, tools/list, усі 11 tools/call у безпечному disabled режимі; health/list_contacts/stop success; desktop/send paths fail closed.
3. **Справжній AT-SPI + GTK:** ізольовані Xvfb/D-Bus, реальний accessibility IPC, text read/write, exact search, local button action, scoped reads. Синтетична кнопка не відправляє повідомлення.
4. **Viber Desktop E2E:** **НЕ перевірено для всіх GUI-шляхів**. Дозволене read-only discovery 2026-10-18 знайшло конкретний blocker: немає Viber/XFCE процесів, X11 socket і accessibility bus socket; історична сесія hannelora `closing`. Дерево реального Viber недоступне. Не читали приватні чати, не вводили GUI, не відкривали інші чати. Немає погодженого тексту для реального `0981901991`.

## Межі, які не можна приховувати

- Прямий AT-SPI EditableText може не підтримуватися Viber Qt. Clipboard fallback зараз не реалізований; не можна видавати GTK success за Viber success.
- Viber може не експортувати stable message ID/outgoing direction або independent self marker. Без них strong send/self verification блокується або повертає unknown.
- Універсальний production UI profile не вигаданий. Потрібна окрема дозволена калібровка на фактичній версії/мові Viber.
- OCR fallback не реалізований у Linux backend; macOS Vision не переноситься. За відсутності AT-SPI читання fail-closed. Тому operational parity для inaccessible UI ще відкрите.
- Мінімальна «людина погодила» церемонія не є захистом від довільного shell того самого UID; для такого threat model потрібен окремий broker.
- Upstream клієнтські демонстрації/команди зберігаються для атрибуції; Linux API використовує `server.py`/`linux_server.py`, а не небезпечні legacy send функції.

Незалежний review додав cancelable polling асинхронної outgoing bubble, повторні identity/draft checks і sanitized reason codes. Це перевірено синтетично; жодного реального send. Replay protection обмежене тим самим approval token: новий token може повторити текст, business-event idempotency немає.

Оновлення 2026-10-18: desktop уже відновлений; цю стару вимогу виконано. Нові blockers: stale AT-SPI socket, відмінна міжнародна форма номера у header, повідомлена Господарем offline-проблема. GUI-проби призупинені на час ручного тесту. Реальний X11 header capture та локальний OCR перевірені; `x11_probe.py` лише діагностика без authorization/write/send і без інтеграції у domain backend. Clipboard fallback та повний operational parity залишаються відкритими.

Історичний наступний крок — Господар відновлює власну desktop-сесію/Viber або окремо погоджує конкретне відновлення. Потім повторити вузьке read-only discovery без читання приватного тексту та відкалібрувати profile за реальними доказами. Лише literal `0981901991`; надсилання тільки після погодження точного тексту. Не тестувати My Notes наживо. OCR/clipboard fallback не додавали без доступного реального UI: історична нотатка про clipboard не доводить безпечної інтеграції чи готовності поточного backend.
