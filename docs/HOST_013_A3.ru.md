# Sedrava Host A3: типизированное чтение и структурированный результат

Экспериментальная интеграция Core #56 и Host A2 #54. **Не релиз и не
публичный сервер.** Текущая реализация host-программ принимает доверенный
исходный код с явными локальными полномочиями; POSIX no-follow операции
не являются полноценным OS sandbox при враждебных параллельных изменениях.

## Первый работающий переход от Host к Core Result

Новая операция \`try_read name from path\` использует общий тип ядра
\`Result<text, HostReadError>\`, где \`HostReadError\` — встроенный
\`error open\` с ID \`sedrava.host.read.v1\`.
Варианты: \`FileNotFound { path: text }\`,
\`PermissionDenied { path: text }\`,
\`InvalidEncoding { path: text }\`,
\`InvalidPath { reason: text }\`,
\`ResourceTooLarge { limit_bytes: int }\`,
\`TextTooLong { limit_scalars: int }\`,
\`IOFailure { operation: text }\`.

После \`try_read\` допустим только терминальный, статически проверенный
\`match\` с максимум восемью чистыми локальными \`let\` и обязательным завершающим \`emit\` в каждой ветке, отступы 4/8 пробелов.
Это узкий A3-адаптер, а **не полная поддержка произвольных блоков Core
в Host**. Используются общие \`ErrorType\`, \`ResultType\`, \`ResultValue\`,
\`ErrorValue\`, \`pattern\`, \`check_arm\`, \`exhaustive\` из Core #56.
Для открытого типа обязательна последняя ветка \`Err(error)\`.
Некорректные, дублированные, недостижимые и неохваченные ветки
отклоняются на этапе разбора программы.

~~~text
host "Safe report"
arg filename: text
try_read file from filename
match file:
    Ok(content):
        emit content
    Err(FileNotFound { path }):
        emit "Нет исходного файла"
    Err(error):
        emit error_id(error)
~~~

Форма пути и штатная ошибка файловой операции дают \`Result\`.
Отсутствие \`--allow-read\` отклоняет запуск до исполнения.
Запрещённая символьная ссылка, специальный файл/несанкционированный
обход каталога — фатальное нарушение политики, **не** \`Err\`.

## HostExecutionResult v1

В CLI добавлена опция \`--result-protocol v1\`, по умолчанию
сохраняется совместимый A2 формат. V1 возвращает валидируемый
машиночитаемый JSON со статусами:

- \`success\` — выполнение и, при необходимости, фиксация закончены;
- \`failed\` — ожидаемая, но не обработанная ошибка операции (включая commit);
- \`fault\` — нарушение политики, неизвестный сбой и другие фатальные ошибки;
- \`rejected\` — невозможно подготовить/проверить запуск, инструкции не исполнялись.

Обязательны \`phase: setup|execute|commit\` и
\`commit_state: not_started|not_applicable|committed|unknown\`.
Ошибка после входа в фазу commit имеет \`commit_state: unknown\` даже если
первое исключение было \`FileNotFound\`: без независимой проверки
состояния безопасный автоматический повтор невозможен.

Протокол намеренно **не включает реальные пути ОС, traceback или текст
Python-исключения**. Все ошибки имеют стабильный \`error.code\`; по
умолчанию \`retryable: false\`. Выдача JSON и проверка валидности
не являются аутентификацией или авторизацией серверного запроса.

~~~sh
mkdir -p build/a3/read
printf 'test' > build/a3/read/example.txt
python sedrava_cli.py host check examples/host_typed_read_013.sdr
python sedrava_cli.py host run examples/host_typed_read_013.sdr \
  --root build/a3 --trusted --allow-read --read-scope read \
  --arg filename=example.txt --result-protocol v1
~~~

Важные ограничения:
- В Host A3 пока только \`try_read\`; записи остаются отложенными A2
  операциями. Новая схема ошибок и пользовательские \`error\`-декларации
  в Host не поддерживаются, встроенный тип закрывает первый реальный кейс.
- Внутри ветки \`match\`: до восьми чистых \`let\` и финальный \`emit\`; файловые и другие побочные операции запрещены.
- \`HostPath\`, каталоговые typed results и двухфазные \`WriteIntent\`
  не реализованы.
- Без web worker, очереди задач, HTTP auth, пользовательских полномочий,
  запуска недоверенного исходного кода и удалённых триггеров.
- Не подменять эффект-манифест Core A1: пока он описывает только app-domain,
  а Host использует собственные реальные capability checks.
- Не объединять PR с main без полного CI и security review.
