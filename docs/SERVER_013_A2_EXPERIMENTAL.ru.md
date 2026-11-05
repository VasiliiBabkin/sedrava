# Sedrava 0.13 A2 — типизированные API и транзакционные CRUD (экспериментально)

**Исходники в отдельном черновом PR. Не опубликовано. Не является механизмом аутентификации пользователей или готовым публичным API.** Базовая версия — успешный PR #48 (A1); для слияния с разрабатываемой 0.12 требуется отдельная интеграция.

Пример в examples/server_013_api_tasks.sdr описывает миграции SQLite и конечный список маршрутов. Доступные действия только list/create/read/update/delete. Каждому пути, таблице и HTTP-методу соответствует единственное допустимое действие; произвольный SQL и Python-код в исходном языке отсутствуют.

Пример:

~~~text
endpoint GET "/api/tasks" -> list tasks
endpoint POST "/api/tasks" -> create tasks
endpoint GET "/api/tasks/{id}" -> read tasks
endpoint PATCH "/api/tasks/{id}" -> update tasks
endpoint DELETE "/api/tasks/{id}" -> delete tasks
~~~

**Выключено по умолчанию.** Для локальных испытаний на loopback необходимо задать одновременно SEDRAVA_API_EXPERIMENTAL_ENABLE=1 и SEDRAVA_API_EXPERIMENTAL_TOKEN с отдельным случайным секретом не короче 32 печатных ASCII-символов. Токен передаётся в заголовке Authorization: Bearer. ASGI проверяет клиентский и серверный loopback-адрес и Host. Сервер запускать только на 127.0.0.1; нельзя открывать этот API через публичный Nginx или переносить токен в браузерный JavaScript. **Один общий токен не заменяет аутентификацию и авторизацию конкретных пользователей.**

~~~sh
# Применяется только к checkout экспериментальной ветки / её отдельному wheel.
sedrava check examples/server_013_api_tasks.sdr
sedrava build server examples/server_013_api_tasks.sdr --output build/server-api
export SEDRAVA_DB_PATH="$PWD/build/tasks.sqlite"
python build/server-api/server.py migrate

# Для изолированного локального испытания:
export SEDRAVA_API_EXPERIMENTAL_ENABLE=1
export SEDRAVA_API_EXPERIMENTAL_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m pip install uvicorn
cd build/server-api
python -m uvicorn server:app --host 127.0.0.1 --port 8000
# В другом терминале (использовать секрет из окружения, не печатать его в журнал):
# curl -H "Authorization: Bearer $SEDRAVA_API_EXPERIMENTAL_TOKEN" \
#      -H 'Host: 127.0.0.1:8000' http://127.0.0.1:8000/api/tasks
~~~

Контракт: JSON-запрос до 8 KiB, запись строго по типизированной схеме int32/bool/text(N), неизвестные и повторные поля отклоняются; для list — limit 1..50, offset до 10000, сортировка по id. Все входные значения передаются в SQLite параметрами. Создание/изменение/удаление — транзакции BEGIN IMMEDIATE с отменой при ошибке. GET отдельной записи возвращает ETag; изменение и удаление требуют If-Match с этим значением. Несовпадение возвращает 409, отсутствие If-Match — 428. ETag определяется хешем текущей записи, не постоянным счётчиком версий; изменение и возврат к прежним значениям не гарантирует обнаружения конфликта ABA. Это ограничение A2.

В A2 нет пользовательских сессий, прав на отдельные записи, токенов доступа пользователей, CSRF-защиты для cookie-сессий (cookie-сессий тоже нет), лимитов частоты запросов, распределённых транзакций и поддержки PostgreSQL. Настройка reverse proxy и реальные публичные приложения запрещены до следующего независимого этапа безопасности. При возникновении ошибки SQLite/схемы API возвращает безопасный код, не выдавая внутреннюю информацию.

Контроль готовности: реальная SQLite и ASGI интеграция, типы/границы JSON, попытки SQL-инъекции, конфликт при параллельном редактировании, запрет удалённых клиентов/неверных токенов, работа после перезапуска, отсутствие регрессий A1, создание wheel/sdist. **NO-GO для публичного многопользовательского приложения.**
