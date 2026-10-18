# Viber у графічному сеансі VPS

## AT-SPI

Якщо `org.a11y.Bus.GetAddress` повертає неіснуючий сокет, спершу перевірити
користувача, DISPLAY, DBUS_SESSION_BUS_ADDRESS та XDG_RUNTIME_DIR. Не підставляти
інший display навмання. У нашому випадку погоджений перезапуск користувацького
`at-spi-dbus-bus.service` та Viber відновив Text interface зі збереженим профілем.
Адреса містила `bus_10.0`; старий шлях `bus` не існував.

`atspi_text_reader.py` запускається окремим системним Python з GI/Atspi typelib.
У private X11 profile можна ввімкнути `atspi_composer: true` та вказати
`atspi_application`/`atspi_window`. Поле `points.composer` повинно лежати всередині
рівно одного видимого Text element. Порівнюються PID, frame geometry й точний
Unicode; OCR не використовується як доказ тексту чернетки. Якщо helper не бачить
однозначного поля, ввід блокується. Наявність Text не означає EditableText.

## Хибний offline при робочій мережі networkd

На перевіреному Ubuntu24.04 VPS eth0 керував systemd-networkd. NetworkManager
мав unmanaged interfaces і стан disconnected. Viber27.3.0.2/Qt6.8 завантажував
`plugins/networkinformation/libqnetworkmanager.so`, тому показував offline.
GLib monitor netlink окремо підтвердив наявність мережі.

Виконаний application-only workaround після погодженого troubleshooting:

1. Зберегти wrapper та SHA256 Qt networkmanager plugin у приватному backup.
2. Перемістити **лише plugin цієї user-scoped інсталяції Viber** за межі її
   plugins/networkinformation. Не змінювати системні Qt plugins.
3. У wrapper перед exec додати `export GIO_USE_NETWORK_MONITOR=netlink`.
4. Після погодженого перезапуску перевірити `/proc/PID/maps`: networkinformation
   використовує `libqglib.so`. Окремо перевірити статус у самому Viber.

Відкат: повернути wrapper та plugin з приватної копії, погоджено перезапустити
Viber. Перевірити фактичний executable/PID; не виконувати глобальний pkill.
Профіль Viber не видаляється. NetworkManager, netplan, firewall та маршрути не
змінюються. Це умовний workaround для перевіреного конфлікту monitor/backend,
а не універсальний засіб для будь-якого offline і не доказ доставки повідомлень.

Джерела: [Qt Network Information](https://doc.qt.io/qt-6.8/qnetworkinformation.html),
[вибір backend у Qt6.8](https://github.com/qt/qtbase/blob/6.8/src/network/kernel/qnetworkinformation.cpp),
[GLib backend](https://github.com/qt/qtbase/blob/6.8/src/plugins/networkinformation/glib/qglibnetworkinformationbackend.cpp).

## RDP та буфер обміну — незавершена діагностика

Після Copy number деякі нові X11-з'єднання зависають ще на handshake.
Звичайні запити й ізольоване встановлення selection можуть працювати.
Root cause не підтверджено. `VIBER_XSEL` дозволяє явно вибрати локальний xsel лише
для clipboard set; читання виконує окремий GTK3 helper із точним UTF8_STRING.
TARGETS перевіряються, plaintext відновлюється,
порожня selection без власника повертається до такого самого стану.
Rich clipboard відхиляється, помилки блокують операцію. Цей шлях не оголошено
стабільним на живому RDP; production input/send вимкнені.

Погоджений тест `disableclipboard=1` після підтвердженого користувачем повторного
входу також завершився ui_command_failed. Чернетка лишилась порожньою, send=0.
Це не підтвердило гіпотезу усунення проблеми через clipboard sync. Параметр
профілю повернуто до0; чинний сеанс повторно не переривався. Файл налаштування
не змінює вже відкритий RDP-сеанс.
Не витягувати пароль і не вважати команду connect успішною без видимого входу
та перевірки збереженого desktop. Перед повтором put_draft прочитати поле.
Невідомий результат send не повторювати, включно з видачею нового token.

## Приватна діагностика без вмісту повідомлень

Для окремого контрольованого процесу можна вказати
`VIBER_DIAGNOSTICS_FILE=/absolute/private/ui-diagnostics.jsonl`. Каталог має
належати поточному користувачу й бути доступним лише йому (0700). Файл
відкривається з0600, O_NOFOLLOW та O_NONBLOCK; публічні файли, symlink і FIFO
відхиляються, розмір обмежено приблизно64KiB. Без змінної журнал не створюється.

Записуються лише time_ns, фіксовані phase/command_kind/failure_kind, числові
returncode/timeout_seconds. Немає raw argv, stdin, stderr, exception text,
номерів, чернеток, токенів або environment. Навмисно не додано автоматичних
retry чи довших тайм-аутів. Worker timeout/exit також мають фіксовану категорію.
Помилка cleanup не підміняє початкову помилку операції; коли сама операція
успішна, невдалий cleanup усе одно блокує результат.

Acceptance helper `scripts/draft_acceptance.py` перевіряє реальний запис і читання
probe у свіжому diagnostic path перед будь-яким UI-кроком тесту. Використовувати
вже наявний0700 state-каталог; назва private сама по собі не доводить права.
Клієнтський процес і MCP server запускаються під тим самим користувачем з тим
самим `VIBER_DIAGNOSTICS_FILE`; це треба перевірити при створенні StdioServerParameters.
Helper не змінює права й не надає погодження на тест.

Передавати exact expected_recipient, bounded `X11Backend.identity` та native
`X11Backend.draft` readers. Helper перевіряє actual health send_enabled=false,
номер і порожнє поле, а RPC put_draft передає expected_recipient для повторної
перевірки на сервері до write. Максимум один put_draft,30 с, без retry.
Невизначений або помилковий результат спершу перевіряється окремим read-only
читанням поля. Погодження потрібне на конкретний обмежений живий тест.

## Відтворені дефекти CLI читання та cleanup

На ізольованому Xvfb встановлений xsel1.2.1 повернув rc0 і0 байтів після
відмови власника у конверсії. Старий reader прийняв це за порожні дані.
Також xsel і xclip можуть переходити з UTF8_STRING на STRING. TARGETS із
UTF8_STRING не доводить, що власник справді віддає відповідний вміст.

Новий `clipboard_reader.py` запитує тільки UTF8_STRING через GTK3; перевіряє
тип, format8, довжину≤1MiB та коректність UTF-8. Коректні0 байтів дозволені;
відмова/інший тип/некоректні дані блокують операцію. Helper має stdin=DEVNULL,
закриті сторонні fd та незмінний зовнішній timeout3с; після timeout завершується
й reaped. Він не змінює selection ownership і не створює daemon.

Якщо збереження початкового clipboard не вдалося, жодних click/key/set/clear
не відбувається. Escape дозволений лише після спроби відкрити меню. Зміна
власника між початковою перевіркою і завершенням snapshot також блокує ввід.
Діагностичні етапи: clipboard_snapshot, identity_copy, clipboard_restore.

Сім режимів fake owner перевірено на новому Xvfb; коректний Unicode, empty,
відмова, STRING fallback, неправильний тип, silence та owner switch.
Це не відновлює дані несправного зовнішнього owner і не доводить усунення
попередніх live тайм-аутів. Реальний clipboard не очищувався.

Джерела: [xsel1.2.1](https://github.com/kfish/xsel/blob/8c89a9225ea898b67c5a067d1a7f8e78f0a458aa/xsel.c),
[Gtk wait_for_contents](https://docs.gtk.org/gtk3/method.Clipboard.wait_for_contents.html).

## Відрізнення selection timeout від ширшого X11 stall

Нові fixed checkpoints у private log: clipboard_init_start (включає GI import),
clipboard_init_ready, clipboard_convert_start, clipboard_convert_done. Done не
означає валідні дані; результат ще перевіряється. Події checkpoint/probe не є
помилками — primary failure визначається серед timeout/exit/os подій.
Діагностичний шлях trial має лишатися свіжим до acceptance preflight: окремі
попередні read-only observations повинні мати інший шлях або вимкнений журнал,
щоб не створити його завчасно. Повторне використання trial path заборонене.

Ізольований silent owner не блокував нові X connections; fake XGrabServer
відтворив reader3s→writer2s→focus3s→search3s. Це модель можливого механізму, не
доказ провини Viber/RDP. Нових live вимірювань не було. Query timeout більше
не перейменовується на відсутність вікна.
