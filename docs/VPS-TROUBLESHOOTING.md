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
Root cause не підтверджено. `VIBER_XSEL` дозволяє явно вибрати локальний xsel
для UTF8 clipboard get/set; TARGETS перевіряються, plaintext відновлюється,
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
