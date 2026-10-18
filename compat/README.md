# Hermes та MCP SDK v2: read-only annotations

Перевірено на встановленому VPS runtime 2026-10-18. Це **підготовлений patch**,
не зміна production Hermes і не дозвіл обходити approval.

`tools/mcp_tool_registration.py::_annotation_read_only_hint` читає тільки
`annotations.readOnlyHint`. У встановленому SDK v2 Python-властивість має назву
`read_only_hint`; wire alias залишається `readOnlyHint`. Тому навіть коректні
read-only tools потрапляють до Hermes як write-capable.

Докази:

- MCP discovery повернув для `health` і `read_visible` wire `readOnlyHint:true`.
- Внутрішній Hermes `captured_hints` записав обидва значення як `false`.
- `trust: untrusted` заблокував `health` до виконання RPC; prompt не підтверджувався.
- На фактичному SDK: `getattr(a,'readOnlyHint',None) → None`,
  `getattr(a,'read_only_hint',None) → True` для тих самих wire metadata.

`hermes-sdk2-readonly.patch` приймає обидві підтримувані форми, але тільки
literal `True`. Missing, `False`, `None`, числа/рядки й конфлікт двох форм
залишають tool write-capable. 15 окремих regression cases проходять; функцію
також перевірено з фактичним SDK v2 VPS, без патчу production і без tool dispatch.

Patch створено для baseline SHA256 модуля:
`10a33536058523140beb8b6e224ef88c30925bea1d4807f7a822096c736b9117`.
`git apply --check` пройшов на копії фактичного модуля.

Після окремого погодження: зберегти приватну резервну копію модуля, повторно
перевірити baseline, застосувати patch, виконати isolated `scripts/hermes_smoke.py`
із `trust:untrusted`, а вже потім погоджений перезапуск потрібного Hermes runtime.
Не замінювати `trust` на `full` для приховування цього результату. Код
`hermes_sdk2_readonly.py` використовується лише тестами; MCP його не імпортує.

Для безпечної діагностики без tool calls підтримано `--inspect-only`:

```sh
HERMES_PYTHON -I scripts/hermes_smoke.py \
  --hermes-root /path/to/installed/hermes \
  --site-packages /path/to/committed/environment/site-packages \
  --entry-json /private/hermes-viber-entry.json --inspect-only
```

Runtime/selected dependency paths потрібно визначати живою перевіркою. Скрипт
не запускає `hermes_bootstrap` (він може автоматично синхронізувати залежності),
не викликає модель і використовує тимчасовий HERMES_HOME. Пропускаються лише
`health` та `read_visible`; input/send примусово вимкнені. Без `--inspect-only`
перевіряється справжній Hermes registry dispatch; `--read-status` додатково
перевіряє live read після калібрування та активації Viber.
