# Завдання

Мета й DoD: [PROJECT.md](PROJECT.md). Єдиний виконавець коду, Viber та VPS —
поточна задача Codex; сторонній огляд не керує цим desktop паралельно.

- [x] Вивчити upstream та наявний Linux-порт; виконати find-skills.
- [x] Встановити погоджений mcp-builder у проєкт.
- [x] Реалізувати MCP stdio, локальний OCR, обмеження UI, ledger та захист від повторів.
- [x] Створити приватний GitHub workflow у наявному репозиторії, draft PR #1.
- [x] Офіційний .deb у user scope; резервна копія і відкат старої інсталяції.
- [x] За погодженням зберегти старий профіль; Господар активував новий через QR.
- [x] Усунути хибний offline-індикатор application-only Qt/GLib workaround.
- [x] Погоджено відновити AT-SPI та перезапустити Viber; Text читання працює.
- [x] Застосувати погоджений SDK2 patch, підключити чотири read-only tools Hermes.
- [x] Перезапустити тільки погоджений Hermes gateway; перевірити actual registry dispatch.
- [x] Негативні тести фокусу, номера, clipboard failure, replay; 160 тестів пройшло.
- [ ] Підтвердити точний Unicode-текст чернетки в живому Viber через MCP.
- [ ] Окремий погоджений тест send із незалежним human approval; перевірка на телефоні.
- [x] Код07320d8: Debian/X11 CI успішний; PR оновлено, лишається draft.

## Поточна перешкода

Зависає X11 connection setup у деяких операціях після Copy number. Не доведено,
що причина — RDP clipboard. Production читання працює окремо від цього шляху.
Господар погодив тест без RDP clipboard sync і підтвердив повторний вхід.
До тесту чернетка була порожня; Viber PID і геометрія збережені. Рівно один
MCP put_draft після reconnect повернув ui_command_failed за4221 мс, SEND=0.
Після збою AT-SPI підтвердив length0; approval ledger порожній. Live read-only
status працює (987 мс). Цей тест не усунув проблему й не встановив її причину.
Параметр Remmina на диску повернуто до початкового0, інші поля збережені;
чинний сеанс не переривався повторно, зміна діятиме при наступному підключенні.

Підготовлено приватну opt-in діагностику command_kind/phase/failure_kind та
збереження первинної помилки при cleanup failure. Це виправлення діагностики,
а не підтверджене усунення X11-збою. 149 unit tests, protocol smoke та ізольований
X11 fixture пройшли; development read-only MCP probe пройшов за1005 мс.
Наступний крок: один обмежений draft-only acceptance test із цією діагностикою,
точний номер/вікно/Unicode. Нових live input/send після попереднього тесту не було.
Критерій успіху: підтверджена точна чернетка й успішний результат MCP.
До live send цей критерій і незалежне human approval обов'язкові.

Додатковий погоджений тест із діагностикою повернув ui_command_failed за11428 мс.
Після нього draft length0, approval rows0. Журнал не створився: помилка підготовки
вибрала каталог0775, який logger правильно відхилив. Перевірено реальний запис
0600 у вже наявному state-каталозі0700 без UI input.

Новий acceptance helper перевіряє реальний probe write/read ДО RPC, actual health
send_enabled=false, поточний номер та порожнє поле. put_draft тепер має optional
expected_recipient із server-side verify до write; тест зміни чату проходить.
RPC обмежений30 с, без retry після timeout/error.149 тестів і protocol smoke
пройшли. Новий live test не запускався; для нього потрібна окрема згода.

## Останній погоджений тест

Corrected helper пройшов diagnostic probe й actual health, але перевірка адресата
зупинилася на clipboard timeout3с. Загалом4694мс; put_draft calls0, draft length0,
approval rows0. Діагностика цього разу збережена. Read-only probes підтвердили
нестабільне отримання clipboard; процес-власник не встановлений.
Пропозиція наступного кроку: за окремою згодою очистити лише CLIPBOARD цього
сеансу та провести один guarded draft-only тест. Поки очищення не виконано.

## Ізольоване виправлення читання clipboard

- [x] Відтворити xsel rc0/empty на відмові власника; старий reader приймав помилку.
- [x] Запитувати точний UTF8_STRING окремим bounded GTK3 helper без STRING fallback.
- [x] Блокувати snapshot при зміні owner; прибрати Escape після невдалого snapshot.
- [x] 160 unit tests, protocol,7 hostile-owner Xvfb cases, full Unicode/restore fixture.
- [x] Додати fixture в X11 CI та описати GTK3 dependency без встановлень на VPS.
- [x] За новою згодою виконати trial VBR-20261018-STRICT-01; зупинився до put_draft.

Попередня спроба4694мс спожита; переказ старої згоди не дозволяє дубль.
Новий trial не очищує реальний буфер. Під час цього етапу не було live UI/read
операцій, змін production, Remmina, тайм-ауту3с чи прав доступу.

## STRICT-01: виконано, згода спожита

11897мс, health1, put_draft0, SEND0, approval rows0. Після Copy number reader
перевищив3с, відновлення clipboard —2с; cleanup перевірка фокусу також timeout.
Буфер до/після читабельний, але відрізняється. Повторного відновлення не було.
Перший post-check вікна не вдався; незалежний AT-SPI post-check підтвердив поле
довжиною0. ExceptionGroup — wrapper; primary event identity_copy/clipboard/timeout3s.
Живий ввід ще не працює. Новий trial/очищення/рестарт не погоджені; поточний
marker виключає повторне використання цієї згоди.

## Пріоритет: справжні збережені контакти

Вимогу narrowed до Viber address book. Feasibility: ручні aliases не підходять;
read-only schema не підтвердила saved-contact provider/chat binding. Новий adapter
або fake allowlist не додано. Details: docs/SAVED-CONTACTS.md. Новий live-огляд
книги потребує окремого погодження; Copy number debugging більше не розширюємо.

Збережені корисні diagnostic fixes: query timeout не означає missing window;
GTK init/convert checkpoints;3 isolated Xvfb stall cases пройшли.166 unit tests
і protocol smoke пройшли; timeout/retry/recipient guards не послаблено.

## Огляд saved contact та Linux-native оцінка

- [x] Підтвердити один exact phone під All contacts із Viber only=true (не Recents).
- [x] Native search readback; offline OCR існуючого crop:1exact phone,confidence91.5.
- [x] Оглянути active Info/header/menu/metadata безCopy/Share/Call/send/clipboard.
- [ ] Довести незалежний contact→active-chat binding; header name недостатній.
- [x] Порівняти доопрацювання та rewrite: Linux runtime не імпортує Mac API.

Рекомендовано вузький Linux proof у цьомуrepo; docs/LINUX-NATIVE-ASSESSMENT.md.
Новий adapter, write bypass чи savedcontacts mode не оголошуються готовими.
Широкі UI-проби припинено після зібраних доказів; нової draft/send згоди немає.
