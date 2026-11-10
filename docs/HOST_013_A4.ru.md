# Sedrava Host A4 — типизированное извлечение текста из JSON

**Только экспериментальная ветка `dev/offline-012`**, не выпуск 0.12.0a1 и не стабильная 0.11. Эта возможность расширяет доверенный локальный POSIX Host A3. Исходный код приложения по-прежнему должен быть доверенным; API/веб-песочницы нет.

## Новый оператор

```text
try_json_get_text result from document at key
```

`document` — ранее проверенное Host JSON-значение, `key` — `text` или `int`. Получается номинальный `Result<text, HostJsonLookupError>` с ID `sedrava.host.json.lookup.v1`. Ошибка **closed** и имеет три варианта без полей:

- `MissingKey`: отсутствует строковый ключ объекта;
- `InvalidIndex`: неверный индекс массива, включая выход за границы или индекс не типа `int`;
- `UnexpectedType`: результат не текст, контейнер не объект/массив либо неверный тип ключа объекта.

Для результата доступен прежний ограниченный статически проверенный `match`: одна терминальная развилка с чистыми `let` и обязательным `emit`. Все варианты закрытой ошибки должны быть покрыты, если нет завершающего `Err(error)`. Синтаксис неперехватываемых ошибок не меняется.

```text
host "Safe JSON title"
arg config: json
try_json_get_text title from config at "title"
match title:
    Ok(text):
        emit text
    Err(MissingKey {}):
        emit "title is missing"
    Err(InvalidIndex {}):
        emit "invalid array index"
    Err(UnexpectedType {}):
        emit "title is not text"
```

Пример: `examples/host_json_typed_013.sdr`.

```sh
python sedrava_cli.py host check examples/host_json_typed_013.sdr
python sedrava_cli.py host run examples/host_json_typed_013.sdr --root . --trusted --arg 'config={"title":"Sedrava"}' --result-protocol v1
python scripts/offline_verify.py quick
python scripts/offline_verify.py full
```

Операция **не читает файлы**. Она работает с уже полученным JSON и не требует `--allow-read`. Однако `read_json` по-прежнему требует `--allow-read` и доступа в соответствующую область.

Строгий исходный JSON сохраняет ограничения A2: ≤4096 байт, 128 узлов, глубина 8, 32 поля на объект, строки ≤1024 Unicode-символов. Ошибки разбора JSON, нарушения политики/полномочий, ошибок движка и бюджетов **не становятся** `Err`. Возврат пустых структур/нестрокового JSON проверяется по типам, без автоматического преобразования.

Старый `json_get_text` остаётся с прежним поведением (ошибка при недопустимом поле). Добавлена только строковая операция; ни `try_json_get_int`, ни `Result<JsonValue,E>`, ни полная поддержка Host action `match` пока не объявлены. Поля error-вариантов пустые, поэтому значение ключа и JSON-данные автоматически не раскрываются. Скрипт может явным `emit` возвращать собственные данные.

Локальный `quick` теперь включает `tests/test_host_a4_json_result.py`. Итоговый статус только по реально исполненным проверкам; без Python/браузер/Android/упаковки на точном SHA полноценное принятие и выпуск **NO-GO**.
