# A27 — независимая приёмка интеграционного кандидата

Forgejo: https://git.virtreal.ru/. Приватные CI-репозитории kontinentus/sedrava-ci и kontinentus/sedravasql-ci; rootless Podman, repository-scoped runner v13.2.2, vds-rust. Изменения не запускают GitHub Actions.

## Диагностика и исправления 27 ноября 2026

- SQL runner: sedravasql-runner.service был inactive/disabled после штатного shutdown 27.11.2026 06:31:25 (UTC+3). Восстановлен через user systemd enable --now; проверены active/enabled и активный статус API. Ранее ожидавшая B37 проверка завершилась успешно; B36 принята в работу. Старые задания не отменялись.
- Sedrava A22, run 3: Forgejo task 7 завершился exit 127. Из сохранённого журнала 2026-11-27T04:06:23.6674861Z: /var/run/act/workflow/1.sh: line 10: python3: command not found. Ошибка подготовки окружения, не компиляции. Новое задание устанавливает python3 в rootless job-контейнере при отсутствии, не на VDS. Python используется только для тестовой оснастки.
- Gateway auto периодически возвращал SSH CONNECTION_FAILED / i/o timeout. Регион подключения изменён на Europe после проверки доступности endpoint, доверия host key и аутентификации; операция server.set_region успешна. SSH/firewall VDS не менялись. Это не гарантия отсутствия дальнейших сетевых ошибок.
- Два контейнера одновременно, каждый около 1.57 GB memory limit по podman stats. Cargo build jobs=1, debug info и incremental выключены для CI. Не повышать параллелизм без проверки ресурсов.

## Происхождение

| Репозиторий | Проверяемый исходный коммит | CI-коммит | Запуск |
|---|---|---|---|
| Sedrava | f688f992f0e6e047b03ffdb968ddd4a454b091fe | 63f291920ef9ca6ef2e3a57df5a46fe9bd86228f | https://git.virtreal.ru/kontinentus/sedrava-ci/actions/runs/4 |
| SedravaSQL | 60a7d0488a23135fa064b7cf2496f93a78b519bd | a65e68dff8f20ae367fd9d4327e423a78174396f | https://git.virtreal.ru/kontinentus/sedravasql-ci/actions/runs/4 |

Обе CI-ветки ci/a27-platform имеют один дополнительный файл .forgejo/workflows/platform.yml относительно точного source SHA. Копии workflow в evidence/a27-forgejo-2026-11-27. Checkout закреплён на ревизии Forgejo checkout. Проверяются HEAD, родитель и единственное изменение, отсутствие хостовой БД Forgejo и docker.sock, версии инструментов. SQL source отдельно закреплён и проверяется, Rust dependencies --locked.

Проверки: SQL root + native all-targets, Sedrava all-targets, alpha smoke, A16 SQL Host, A17–A25 HTTP/migration/project acceptance. В новом CI DOM выключен явно; ранее пройденный jsdom на VDS относится к A26, не A27. Это debug qualification, не release build, подпись или публикация. 

## Статус на последнюю проверку API

- B37 (SQL run 2): success, подтверждён сохранённым логом task 8, обе группы тестов без ошибок.
- B36 (SQL run 3): running.
- Sedrava A27 (run 4): running.
- SedravaSQL A27 (run 4): waiting.
- Оба runner active/enabled; 23 GB свободно на VDS при двух активных сборках.

Вердикт: инфраструктура восстановлена, новый CI опубликован и запущен. A27 qualification не завершена; для GO требуются success обоих run 4 с точными SHA из таблицы и проверка журналов. Не считать старую успешную B37 сборку приёмкой A26. Main, release tags, действующие сайты и базы не менялись.
