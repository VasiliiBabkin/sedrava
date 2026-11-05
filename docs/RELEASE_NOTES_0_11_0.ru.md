# Sedrava 0.11.0 — опубликованная стабильная версия

**Выпущена 5 ноября 2026 года:** [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) · [PyPI](https://pypi.org/project/sedrava/0.11.0/). Тег указывает на проверенный коммит `c9cde75e3d2e2c7eafeeaec10c73fec627816e68`, код объединён с main через [PR #44](https://github.com/VasiliiBabkin/sedrava/pull/44). Предыдущие [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)) и стабильная [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) доступны.

Установка в отдельное виртуальное окружение Python 3.10+:

```sh
python -m pip install --upgrade sedrava==0.11.0
sedrava --version
```

## Что реализовано

- Адаптивные многостраничные сайты через `sedrava build site`, переиспользуемые проверяемые компоненты, стили и локальные ресурсы.
- Типизированные WebApp через `sedrava build webapp`: состояния, действия, чистые функции, коллекции, маршруты, формы, таблицы и диалоги.
- Ограниченный клиент HTTP GET/POST/PUT/PATCH/DELETE с проверкой схем. Сервер и API предоставляются отдельно.
- Четыре примера: сайт, задачи, каталог и CRM.
- Сохранена проверенная совместимость прежних приложений/Web/Android; Android versionCode `11002` (RC: 11001, 0.10: 10003).

## Проверки

- 36/36 успешных проверок исходного коммита и 11/11 — после объединения с main.
- Проверены исходники, wheel/sdist, контрольные суммы и чистые установки.
- Реальные установки 0.10.0 → 0.11.0 → 0.10.0 и 0.11.0rc1 → 0.11.0 → 0.11.0rc1 в Python.
- Испытания Chromium, Firefox, WebKit и обновления отладочного APK на эмуляторе Android API35.
- Опубликованный wheel SHA-256 `5780c3cb14f33b95689c518809254e269a3396bb02720e88f9407b9abbd24626`; sdist — `453096116a9da834c4db9023069962cc0d5bf18acb88e403994ad61a339ef70b`.
- [Публикация GitHub/PyPI](https://github.com/VasiliiBabkin/sedrava/actions/runs/41951910157) прошла успешно.

## Ограничения

Язык остаётся экспериментальным, без промышленной сертификации. Нет встроенного доверенного сервера, SQLite/PostgreSQL, аутентификации, разграничения прав, автоматических миграций, подтверждённой работы на физическом Android и гарантий отката производственного APK. Пространства имён и пакеты 0.12 пока отдельно. [Критерии выпуска](STABLE_RELEASE_GATES_011.md) · [Этапы](RELEASE_TRACK_011.md) · [Совместимость](COMPATIBILITY_010.md).
