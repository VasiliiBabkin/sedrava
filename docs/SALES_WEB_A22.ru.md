# A22 — локальное веб-приложение продаж

Нативный Sedrava server раздаёт только три явно заданных UTF-8 ресурса (/, /ui-script, /ui-style) из каталога --web-ui. POST API из sales_api.sdr работает на том же origin. NativeLog — штатное SQLite-free хранилище. Не добавлено новый SQL backend. Закреплена прежняя проверенная зависимость 363ccbc9542ed8e3ecf41e3619f78823ffeb97d4. UI написан на HTML/CSS/JS, не сгенерирован Sedrava. API и запросы описаны на Sedrava.

## Запуск

Linux, исходники текущей ветки, собранные sedrava и sedravasql-native-preview в PATH. Создайте отдельный приватный каталог; следующие команды рассчитаны на новую тестовую базу:

```bash
umask 077
DEMO="$(pwd)/examples/sales_demo"
DATA="$(mktemp -d)"
sedravasql-native-preview init "$DATA/sales.log"
i=0
while IFS= read -r sql; do
  i=$((i+1))
  sedravasql-native-preview sql "$DATA/sales.log" "$sql" "demo-schema-$(printf '%04d' "$i")"
done < "$DEMO/schema.sql"
python3 - "$DATA" <<'PY'
import hashlib,json,secrets,sys
from pathlib import Path
p=Path(sys.argv[1]); rows=[]
for role in ('read','write'):
    token=secrets.token_hex(32)
    (p/(role+'.token')).write_text(token+'\n')
    rows.append(dict(id=role,sha256=hashlib.sha256(token.encode()).hexdigest(),role=role))
(p/'auth.json').write_text(json.dumps(rows))
PY
sedrava database-api run "$DEMO/sales_api.sdr" --database "$DATA/sales.log" --trusted --allow-write --auth-file "$DATA/auth.json" --web-ui "$DEMO/ui" --port 8080 --max-requests 1000 --idle-ms 120000
```

Откройте http://127.0.0.1:8080 на машине запуска; ключ из read.token/write.token вводится вручную. Храните ключи вне каталога UI, не добавляйте их в Git. Не передавайте auth-файл или произвольные данные через --web-ui. Содержимое UI доступно без ключа, API защищён. Ресурсы доверенные, каталог и его родители должны быть контролируемыми оператором. Отвергаются symlink на конечных компонентах, неподходящие типы/размеры; произвольные URL не превращаются в файловые пути. Строгий CSP, no-store, nosniff, deny framing, loopback Host. Не выставлять через reverse proxy: это локальный single-writer preview. После graceful завершения можно повторить только команду run с тем же DATA. При аварии старый lock требует проверки владельца/процесса; не удалять вслепую. Не использовать ценные данные.

## Проверки

```bash
export SEDRAVA_NATIVE_BIN=/absolute/sedrava
export SEDRAVASQL_NATIVE_BIN=/absolute/sedravasql-native-preview
python3 -B scripts/verify_sales_web_a22.py
# Дополнительно: node 20+, установленный jsdom 27.2.0; NODE_PATH на каталог node_modules
SEDRAVA_A22_DOM=1 python3 -B scripts/verify_sales_web_a22.py
```

Реальный HTTP, auth, статические ресурсы, CSP, отказ symlink, перезапуск, проверка БД; DOM-тест с реальным HTTP проверяет формы, роли, безопасный textContent, потерю ответа после commit и повтор с тем же ключом, коррекцию, оплату, атомарную запись и rollback, очистку состояния и отсутствие browser storage. jsdom не браузер: реальная проверка CSP/рендеринга Chromium ещё нужна. A17–A21 63/63. Логи в evidence/a22-sales-web-2026-11-27. После уточнения лимита списков и экранирования pattern повторный DOM и HTTP прогон PASS.

## Ограничения

Списки до 100 записей, не полный CRUD (нет удаления/редактирования товара), нет полноценного управления пользователями, TLS, sessions, concurrency, платежного процессинга. Числовые ограничения форм — клиентские, серверный SQL не гарантирует неотрицательность сумм; необходимы реальные серверные бизнес-правила в A23. Авторизация роли проверяется сервером; UI не скрывает все формы от reader. Данные ключа и pending idempotency только в памяти страницы: после перезагрузки нельзя автоматически гарантировать тот же request key. У NativeLog лимиты 64 MiB/65536 транзакций и один писатель. Это локальная демо-система, не production.

Финальный контроль: 83 Rust tests PASS, A22 DOM/HTTP и A17–A21 PASS. Строгий Clippy не пройден: 14 замечаний в прежнем коде библиотеки и ещё одно в прежнем тестовом коде. Новое замечание A22 о числе аргументов устранено.
