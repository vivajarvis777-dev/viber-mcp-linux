# Viber MCP Linux для Hermes

Linux-порт [wawimundo/viber-mcp](https://github.com/wawimundo/viber-mcp) для Debian/Ubuntu.
MCP працює поряд із Viber Desktop на VPS через stdio. Локальні AT-SPI або X11 +
Tesseract забезпечують доступ до видимого інтерфейсу без хмарного OCR.

**Стан 2026-10-18:** прототип із 14 MCP-інструментами. 106 автоматичних тестів і
справжній MCP handshake проходять. X11/OCR, Unicode з emoji/новими рядками,
відновлення plaintext-буфера й кнопка пройшли тест на ізольованому GTK/Xvfb.
GitHub CI пройшов у Debian Bookworm/Python 3.11 та Ubuntu 24.04/X11.
Живе читання статусу Viber через MCP також перевірене: медіана 891 мс (3 виклики).
За дорученням Господаря AppImage на VPS замінено файлами офіційного .deb 27.3.0.2
у користувацькій інсталяції, зі збереженням профілю та відкатом.
Перевстановлення зі старим профілем не усунуло `No internet connection`.
Після окремого погодження старий профіль збережено, новий відкрив екран активації;
очікується ручне сканування QR телефоном. Online messaging ще не підтверджено.
Надсилання справжніх повідомлень не перевірене й типово вимкнене.
Встановлений Hermes також потребує [виправлення SDK2 annotations](compat/README.md);
patch підготовлено і протестовано, але production ще не змінено.

## Швидкий старт

```sh
uv sync --locked
uv run pytest -q
uv run python tests/protocol_smoke.py
uv run python server.py
```

Без змінних GUI доступні `health`, `list_contacts`, `stop`; решта дій блокуються.
Для Hermes див. [покрокову інструкцію](docs/DEBIAN-HERMES.md),
[конфігурацію](examples/hermes.yaml) та [приклад read-only профілю](examples/x11-profile.example.json).

## Інструменти

| Інструмент | Призначення |
|---|---|
| `read_visible(region)` | Локальний OCR видимої розмови, sidebar, header або status; без навігації |
| `list_chats()` | Видимі назви/прев'ю; це не повний список усіх чатів |
| `read_open_chat()` | Читання з повторною перевіркою точного номера |
| `open_chat(to)`, `open_and_read(to)` | Точний пошук і перевірка адресата |
| `search_and_open(name)` | Лише єдиний точний результат; ім'я не є доказом адресата |
| `put_draft(text)` | Чернетка з точним Unicode readback; інша чернетка захищена |
| `send_message(to,text,...)`, `reply(text,...)` | Одноразово погоджене надсилання |
| `open_my_notes()`, `save_to_my_notes(...)` | Лише AT-SPI з незалежним self-маркером; X11 не підтримує |
| `list_contacts()` | Приватні явні аліаси |
| `health()`, `stop()` | Діагностика конфігурації та скасування worker |

Всі 11 upstream назв збережені. Linux додає явні обмеження безпеки;
[матриця](PARITY.md) відрізняє API-паритет від живої працездатності.

## Принципи

- Read-only спочатку. Ввід і надсилання мають окремі opt-in та калібрування.
- Точний номер, незалежне погодження recipient+text, ledger для захисту від replay.
- Порожнє поле вводу, спливання таймера або ім'я в sidebar не підтверджують адресата.
- Український текст, emoji та нові рядки звіряються clipboard readback, а не ASCII OCR.
- На X11 `sent:null` після кліку означає невизначений результат. OCR не дає stable
  message ID, тому `sent:true`/доставка не вигадуються. Повтор за тим самим token не відправляє знову.
- `stop` доступний, поки OCR працює: блокувальну роботу винесено з event loop.
- Скріншоти не зберігаються; runtime/profile/контакти/токени не комітяться.
- Вікно має бути на передньому плані. Один desktop — один активний контролер.

[Архітектура та аналіз оригіналу](docs/ARCHITECTURE.md) ·
[Debian/Hermes, калібрування, відкат](docs/DEBIAN-HERMES.md) ·
[Докази тестування](EVIDENCE.md)

## Межі

Потрібна активна X11-сесія користувача. Wayland і сервер без GUI не підтримуються.
Читається лише видиме; історія поза екраном, вкладення, дзвінки та фоновий inbox
не реалізовані. Профіль прив'язаний до реальної геометрії/масштабу/панелей.
Точний телефон має бути видимий для контрольованого надсилання; довільні групи
або контакти з прихованим номером поки доступні для читання, але не автоматичного send.
Same-UID unrestricted shell не ізольований від локального approval ledger.

## Походження

Оригінал: Wawi del Mundo, MIT; [LICENSE](LICENSE) збережено.
Base upstream: `af1d0ed1b880dc28a18f2d5198a4d09b52047bd4`.
Успадкований Linux-порт: `da06874c901521845575dd7c7eabc9524c5771ac`.
macOS-файли й [старий README](README.upstream.md) залишено для атрибуції.
Linux entrypoint — `server.py → linux_server.py`; `viber_send.py` — старий macOS domain.
