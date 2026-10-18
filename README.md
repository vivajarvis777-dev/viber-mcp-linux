# Viber MCP Linux

Linux-порт [wawimundo/viber-mcp](https://github.com/wawimundo/viber-mcp) з усіма **11 назвами інструментів upstream**, реальним AT-SPI backend і захистом від непогодженого надсилання. MIT / авторство Wawi del Mundo збережені. Базовий SHA: `af1d0ed1b880dc28a18f2d5198a4d09b52047bd4`.

**Поточний стан 2026-10-18:** desktop відновлений; живий Viber спочатку мав видиме вікно. Read-only X11 header capture + локальний Tesseract справді прочитали один телефон, але він НЕ дорівнює дозволеному literal `0981901991` (міжнародна форма; відповідність не припускалася). AT-SPI GetAddress повертає відсутній socket — Qt-дерево поки недоступне. Пізніше вікно перестало знаходитися; процес залишився. Після повідомлення Господаря про offline/невдале ручне повідомлення GUI-проби зупинені. HTTPS працює, TCP Viber established, але messaging/session успіх не доведений. Немає жодного нового send, зміни draft чи restart. Додано **read-only OCR calibration**, не готовий OCR/clipboard backend. Повний operational port ще НЕ завершений. Деталі нижче та в останньому розділі EVIDENCE.

**Історичний baseline:** domain-тести, справжній MCP stdio і реальний AT-SPI на ізольованому синтетичному GTK-застосунку перевірені. **Працездатність саме на Viber Desktop ще НЕ підтверджена.** Read-only discovery 2026-10-18: немає процесів Viber/XFCE, socket історичного X11 display та accessibility bus відсутні; сесія hannelora `closing`. Тому Qt EditableText і реальні селектори не перевірені; profile не вигаданий. Приватні чати не читалися, GUI input і відправлення не виконувалися. Це не завершена desktop E2E-паритетність. Успадкований `CLAUDE.md` застарілий (його виправлення заблокував захист instruction-файлів); актуальні Linux-статус і команди — тут, у `PARITY.md` та `EVIDENCE.md`.

## Запуск без доступу до GUI

```sh
uv sync --locked
uv run python server.py
```

Transport — лише stdio. stdout зарезервовано для MCP. `health`, `list_contacts` без налаштованого файла, `stop` безпечні без дисплея. За замовчуванням GUI і надсилання вимкнено. Linux ніколи не імпортує старі macOS евристики; оригінальні файли залишені для атрибуції та інших платформ (`README.upstream.md`, `upstream_server.py`, `viber_send.py`, `backends/`). Не використовуйте `viber_send.py` як Linux entrypoint.

## Архітектура

`server.py → linux_server.py (FastMCP) → linux_domain.Service → linux_backend.LinuxBackend → atspi_worker.py → GI AT-SPI`.

- Кожна UI-операція — окремий короткоживучий процес `/usr/bin/python3`, timeout 8 секунд; міжпроцесний `flock` і thread mutex охоплюють усю domain-транзакцію. Очікування mutex обмежене 2 секундами. Загальний час транзакції — сума обмежених викликів, не один глобальний 8-секундний deadline.
- Unicode вводиться через AT-SPI EditableText, з точним readback, а не ASCII-сигнатурою чи xdotool typing. Clipboard, миша та modifier keys не використовуються. Persistent grabs/служби/cua-driver відсутні.
- `stop` позначає поточну операцію скасованою та вбиває worker; наступні операції починають нову транзакцію. Немає клавіш, які залишаються натиснутими. Невідоме завершення надсилання не повторюється.
- Читання обмежене селектором `conversation` або `sidebar`; clipboard та повне вікно не знімаються. OCR не використовується як доказ адресата/доставки. Поточний backend AT-SPI-only: якщо Viber не експортує потрібні інтерфейси, він зупиняється, а не вдає OCR-успіх.

## Налаштування GUI — тільки після окремого дозволу на desktop-приймання

Потрібні Linux X11 desktop із accessibility bus, системний Python з `python3-gi`, бібліотека `libatspi2.0-0` і typelib `gir1.2-atspi-2.0`. На цій машині typelib для синтетичних тестів розпаковано лише користувацьки, без sudo та зміни системних пакетів.

Змінні:

| Змінна | Призначення |
|---|---|
| `VIBER_ALLOW_GUI=1` | явне ввімкнення GUI; відсутня — блокування |
| `VIBER_UI_PROFILE` | абсолютний шлях до приватного, перевіреного profile |
| `VIBER_ATSPI_PYTHON` | Python із GI; типово `/usr/bin/python3` |
| `GI_TYPELIB_PATH` | лише якщо typelib встановлено користувацьки |
| `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS` | перевірена користувацька графічна сесія; не копіювати історичні значення |
| `VIBER_CONTACTS_FILE` | приватний JSON `{ "alias": "exact-phone" }` |
| `VIBER_STATE_DIR` | приватний каталог 0700, типово `~/.local/state/viber-mcp-linux` |
| `VIBER_ENABLE_SEND=1` | надсилання можливе лише разом із незалежним approval token |

Profile містить `application`, `window: {role,name}`, `selectors` із шляхами **прямих дочірніх** accessible вузлів `{role,name,description?}`: `identity`, `composer`, `search`, `results`, `conversation`, `sidebar`, `send`. Кожен сегмент мусить знайти рівно один вузол. `identity` повинен бути номером у contact details, не display name/placeholder. `self_description` — незалежний маркер self-chat, підтверджений самим застосунком; назва «My Notes» не є доказом. `outgoing_message` — selector row, `message_id_attribute` — стабільний ID повідомлення (типово `message-id`).

**Не вигадуйте production profile.** Синтетичний тест генерує profile лише для свого GTK-вікна; він не підходить для Viber. Чи Viber експортує EditableText, independent self marker, outgoing direction і stable message ID — наразі невідомо. Якщо ні, потрібна додаткова адаптація після дозволеного дослідження; не послаблювати перевірку. Особливо не видавати порожній composer за доказ надсилання.

## Адресат і безпека надсилання

- Literal `0981901991` зберігається без змін. Код **не додає** `+`, країну чи інший префікс. Національний literal і E.164 — різні ідентифікатори; невідповідність UI блокує дію. Відповідність між ними не припускається.
- `search_and_open` відкриває лише єдиний **точний** результат. Без alias mapping повертає observed phone із contact-details і `recipient_verified:false`, `send_authorized:false`; display name не стає дозволом на надсилання. Prefix/substring fallback upstream навмисно вилучений.
- Існуючий інший draft не стирається і не замінюється. Його треба змінити вручну. Ідентичний draft можна повторно перевірити. Search field зберігається і відновлюється.
- Усі send-шляхи, включно з `reply` і My Notes, потребують **одного незалежного людського погодження точного recipient+text**. MCP інструмента approve немає. `reply(text)` залишає назву/базовий аргумент upstream, але для реальної дії вимагає додаткові `to` та `approval_token`.
- Людина запускає `uv run python approve.py --recipient <exact-literal>` у своєму терміналі, вводить точний текст у JSON-форматі й підтверджує його. Схвалення живе 5 хвилин, витрачається один раз. Код не зберігає текст/адресата у ledger, лише digest, token і terminal state. Токен не комітити/не логувати.
- Ця церемонія відділяє MCP від погодження, **але не ізолює зловмисний процес того самого Unix-користувача**: якщо агенту дозволений unrestricted shell, політика має забороняти йому запускати approve або змінювати ledger. Для ворожого same-UID процесу потрібен окремий broker/UID, не реалізований тут.
- Стани: `blocked` (не намагалися), `sent` (нова outgoing bubble зі stable ID, точним Unicode та порожнім composer), `unknown` (клік/timeout без достатнього доказу). `delivered` завжди `null`: UI не доводить доставку адресату. Claim зберігається **до** GUI: crash/replay **того самого token** не запускає повторне надсилання. Це не business-event idempotency: новий погоджений token дозволяє повторити той самий recipient+text.
- Після єдиної send-дії — лише cancelable polling (типово 3 секунди, інтервал 0.1 секунди), з identity/draft recheck до й після читання bubbles. Інший draft/recipient негайно дає `unknown`; deadline без доказу — `reason:verification_timeout`. Немає повторного click, write чи navigation. Кожний backend IPC має окремий timeout 8 секунд: бюджет polling не є end-to-end deadline транзакції; поточний цикл може завершитися пізніше. `stop` будить очікування і вбиває поточний worker.
- `blocked`/`unknown` повертають лише allowlisted `reason` (наприклад, `editable_text_unsupported`, `text_interface_missing`, `selector_missing_or_ambiguous`, `recipient_changed`, `draft_changed`, `cancelled`). Невідомі exceptions згортаються до `operation_failed`; приватний текст помилок не повертається.
- Верифікація виконується також усередині worker безпосередньо перед write/send. UI не є атомарною транзакцією щодо дій людини: не користуйтеся Viber паралельно під час дозволеного тесту.

Для цього завдання **ніякий outbound draft не погоджений**. Дозволений майбутній реальний тестовий literal лише `0981901991`. My Notes не є дозволеним тестовим адресатом.

## Launcher і read-only X11/OCR калібрування

`desktop/Viber.desktop.in` відповідає перевіреному desktop launcher. Генератор підставляє абсолютний AppRun поточного користувача, підтримує пробіли, відхиляє небезпечні Desktop Entry metacharacters; **не перезаписує** наявний файл і не запускає програму:

```sh
/usr/bin/python3 install_launcher.py --output "$HOME/.local/share/applications/Viber.desktop"
desktop-file-validate "$HOME/.local/share/applications/Viber.desktop"
```

Не запускати повторно поверх існуючого Desktop/Viber.desktop. Trust/autostart installer не змінює.

`x11_probe.py` — окрема opt-in діагностика, НЕ заміна backend. Потрібні system Python з Pillow, xdotool і Tesseract з eng data. Вона перевіряє єдине видиме Viber-вікно, foreground, власний UID/процес Viber, незмінну геометрію; захоплює тільки configured header rectangle у пам’ять. Не торкається clipboard, не генерує input, не повертає raw OCR/private text. OCR завжди `recipient_verified:false`, `send_authorized:false`, навіть при точному збігу. Overlay/occlusion та помилки OCR не дозволяють використовувати цей результат як доказ identity.

Приватний JSON profile: `{"window_size":[950,780],"header_rect":[294,10,326,73]}` — геометрія спостереженого вікна, **не універсальний profile**. Перед запуском після ручного тесту перевірити актуальну геометрію й дозвіл на header capture; не зберігати profile у Git.

```sh
VIBER_ALLOW_GUI=1 /usr/bin/python3 x11_probe.py --profile /private/header-profile.json --recipient 0981901991
```

`VIBER_TESSERACT` може вказувати користувацький binary; потрібні відповідні `LD_LIBRARY_PATH` та `TESSDATA_PREFIX`, якщо пакети лише розпаковані. На цьому host залежності розпаковані без sudo у `~/.local/opt/viber-mcp-ocr`; системні пакети не змінено. CLI capture pipeline ще не пройшов live end-to-end: протестовані фактичний header capture і його OCR окремо, потім вікно зникло та GUI призупинено. Не використовувати діагностику під час ручної роботи Господаря.

## Відтворення тестів

```sh
uv run python -m pytest --cov=linux_domain --cov=linux_backend --cov=linux_errors --cov-report=term-missing -q
uv run python tests/protocol_smoke.py
# Окремий Xvfb і приватний D-Bus, ніколи не активна сесія Viber:
GI_TYPELIB_PATH=/home/hannelora/.local/opt/viber-mcp-atspi/usr/lib/x86_64-linux-gnu/girepository-1.0 \
  dbus-run-session -- /usr/bin/python3 tests/synthetic_desktop_smoke.py
```

Синтетичний desktop-тест потребує також GTK3, `Xvfb`, `dbus-run-session` та `TMPDIR` у дозволеному scratch. Він сам закриває GTK і Xvfb; D-Bus завершується разом із `dbus-run-session`. Локальна кнопка «Synthetic Send» змінює тільки GTK-widget, не викликає Viber/network. Наприкінці D-Bus інколи пише `A connection to the bus can't be made` від допоміжного GVfs після завершення bus; тест завершується exit 0.

Детальна матриця: [PARITY.md](PARITY.md). Фактичні результати: [EVIDENCE.md](EVIDENCE.md). Секрети, UI profiles, контакти, state, сесії, знімки екрана не комітити.
