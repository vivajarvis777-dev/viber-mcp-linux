# Linux-native: найменший наскрізний доказ

Рекомендація: зібрати один вузький Linux-сценарій у цьому репозиторії, зберігши
перевірені компоненти. Повний rewrite зараз не має доведеної переваги: головні
перешкоди — дані й поведінка самого Linux Viber, а не Mac API.

`server.py` на Linux імпортує linux_server. У Linux-шляху немає Cocoa, Quartz,
Vision або osascript. Три pyobjc залежності обмежені sys_platform=='darwin'.
Mac-файли збережені для атрибуції; успадковані радше назви11tools та загальна
модель UI/OCR/clipboard. Наявний backend уже використовує AT-SPI, X11, GTK3 і
локальний Tesseract. SQLite тут також використовується для approval ledger,
не як підтверджений reader адресної книги Viber.

| Варіант | Практичний наслідок |
|---|---|
| Нарощувати всі14tools | Збільшує поверхню перевірки, не розв'язуючи contact→chat і live writer. |
| Переписати все з нуля | Повторно створює stdio, guards, cancellation, approval/replay; стикається з тим самим Qt UI. |
| Вузький Linux-сценарій у наявному repo | Залишає перевірене ядро, концентрується на одному реальному saved contact і одному повідомленні. Рекомендовано. |

Що зберегти: MCP stdio/Hermes compatibility, async offload, mutex/flock, explicit
recipient/text checks, consent ledger/no-retry, local OCR, native Text reader,
fixed private diagnostics. Mac API parity, My Notes та широку history/search
підтримку відкласти до першого реального наскрізного доказу; джерела/ліцензію не
видаляти. Не використовувати вручну наповнений alias файл як saved-book proof.

| Ланка | Доказ зараз | Що ще потрібно |
|---|---|---|
| Saved contact | All contacts/Viber only, один точний phone; native search readback і OCR crop91.5 | Відтворюваний scoped lookup із rejection неоднозначності; не змішувати Recents. |
| Correct active chat | Вибір цього рядка та відповідний header name | Незалежний phone або доведений native row→chat binding. Ім'я саме по собі недостатнє; це чинний блокер. |
| Exact Unicode draft | Native Text composer читається; синтетичний GTK clipboard Unicode/newlines пройшов | У справжнього Viber немає EditableText. Точна жива чернетка ще не створена. |
| Send/receive | Approval/replay логіка й синтетична кнопка перевірені | Окремо погоджений один send; незалежний доказ на тестовому телефоні. Доставку не виводити з порожнього поля. |

Перший proof: один справді збережений тестовий контакт → підтверджений active
chat → одна погоджена Unicode-чернетка з точним native readback → окремий send
і перевірка отримання. На першій непідтвердженій ланці зупинитися. Зараз це
active-chat binding, тому новий draft/send не запускаємо. Якщо є лише ручне
підтвердження active chat, це окремо погоджений assisted-пілот, а не готовий
автономний режим.

Для writer кандидат на мінімальний прототип — AT-SPI composition input, який
уже спрацював для ASCII пошуку. [API](https://docs.gtk.org/atspi2/func.generate_keyboard_event.html)
приймає UTF-8 STRING, але наш live доказ поки тільки ASCII в search, не Unicode
composer. Його треба перевірити окремо, не приписувати властивості synthetic
EditableText реальному Viber. Перший текст — одна погоджена лінія без Enter;
emoji/нові рядки не оголошувати підтриманими до перевірки відсутності accidental
send. Clipboard paste залишається окремим кандидатом, а не автоматичним fallback.

Persistent X connection, інший input helper або нова оболонка не є доведеним
лікуванням X-server stall. Isolated server-grab модель відтворила каскад тайм-аутів,
але реального винуватця не встановлено. Потрібна одна наскрізна перевірка після
усунення binding-блокера, а не нові десятки tests навколо непідтвердженого шляху.
Production залишається read-only; нові живі draft/send не погоджені.
