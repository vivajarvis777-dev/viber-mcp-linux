# Збережені контакти: результат обмеженого огляду

Вимога: тільки наявні записи адресної книги Viber; жодних нових адресатів.
Стан: джерело saved membership підтверджене для одного тестового контакту;
зв'язок цього запису з активним чатом без Copy number ще не доведено.

## Що реально підтверджено

Офіційний маршрут [Viber Contacts](https://help.viber.com/hc/en-us/articles/9067559172253-Sync-and-manage-contacts):
Compose біля Search → Viber only; список синхронізується з телефоном.
У Linux27.3.0.2 цей picker відкрився. Native Press спочатку повернув timeout,
але наступний огляд довів, що дія вже застосувалась; повторного Press не було.

У фокусоване поле Search name or number введено тільки тестовий номер через
AT-SPI keyboard STRING, без clipboard і Enter. Native Text readback точно збігся.
На actual UI є один рядок із цим номером **під All contacts**, Viber only увімкнено
(візуально та native CHECKED=true). Рядок над All contacts із Recents не брався
як доказ. Офлайн OCR вже збереженого crop знайшов All contacts і один точний
номер із confidence91.5. Нового live capture для OCR не виконувалось.

Це genuine UI evidence membership, а не ручний alias whitelist. Повний provider
ще не реалізовано; результат не доводить відсутність дублікатів у всій книзі.

## Що не вдалося підтвердити

Точний рядок відкрито view-only натисканням; відкрито Info потрібного видимого
чату. Його header name узгоджувався з рядком, але це саме по собі не є binding.
У перевіреному Info зверху/знизу номера не видно. Public metadata22 scoped nodes
не містили очікуваного номера в name/description/attributes/accessible ID.
Accessible IDs мають вигляд QML widget-class hierarchy, а не contact key.
Контекстне меню показує Copy name/Copy number; phone у label/description не
експортується. Меню лише переглянуто й закрито, Copy не натискалося. Hover над
header name не показав tooltip. Relation probe не завершився в межах9с; це
**не доказ відсутності relations**.

Поточний контакт не встановлюємо лише за ім'ям, selected style чи фактом старого
чату. Дублікати імен/неоднозначний результат мають блокувати майбутній write.
Для stable key досить точного phone, прихований UUID сам по собі не потрібен;
але незалежна ознака active chat або доведений native binding поки відсутні.

## Інші перевірені джерела

Код list_contacts читає тільки ручний VIBER_CONTACTS_FILE alias→phone; це не book.
Read-only immutable schema: config.db — Accounts/UserSettings/CommonSettings;
data.db — Key/Category/Value. Namespace metadata не дали contact/address/chat/
conversation match; selected/chat/contact-related settings titles також не
знайдені. Значення акаунта, токени, ключі й повідомлення не читались. Відсутність
SQLite header у третьоїDB не доводить шифрування; формат не припускається.

## Межі виконаного

Дозволений огляд змінював лише view/search/filter, відкривав наявний контакт та
Info, прокручував і переглядав контекстне меню. Message composer не заповнювався;
Copy number/Share/Add/Call/send/clipboard API не викликались. Контакти, доступ,
production і Remmina не змінювались. Timeout дії не трактувався як доказ, що
дія не відбулася: результат перевірявся окремим view. Фото/crops приватні, позаGit.

Режим saved-contacts-only **не готовий до write**. Мінімальна наступна задача —
довести active-chat binding або погодити явний assisted-пілот із ручним
підтвердженням цієї ланки. Не видавати такий пілот за автономну гарантію.
Зняття clipboard identity не усуває clipboard paste у поточному writer.
Архітектурна рекомендація — [Linux-native assessment](LINUX-NATIVE-ASSESSMENT.md).
