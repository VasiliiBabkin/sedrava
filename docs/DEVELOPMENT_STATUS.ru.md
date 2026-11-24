# Состояние разработки Sedrava / SedravaSQL

## Контрольная точка B31 · 24–25 ноября 2026

**Публичные выпуски не менялись:** [Sedrava 0.12.0-alpha.2](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.2), [SedravaSQL 0.1.0-alpha.1](https://github.com/VasiliiBabkin/sedravasql/releases/tag/v0.1.0-alpha.1), Linux x86-64 GNU. Rust — единственная развиваемая реализация Sedrava. Ни один выпуск не объявлен стабильным.

| Контур | Проверенная основа | Состояние |
|---|---|---|
| Sedrava main | [896685c](https://github.com/VasiliiBabkin/sedrava/commit/896685ce31f915d1ab69223f98451c2504792cf7) | 83 Rust-теста, 63 HTTP-запроса A17–A21 |
| SedravaSQL main | [363ccbc](https://github.com/VasiliiBabkin/sedravasql/commit/363ccbc9542ed8e3ecf41e3619f78823ffeb97d4) | NativeLog SQL B28, 67 тестов, Clippy PASS |
| Хранилище research | [a98e709](https://github.com/VasiliiBabkin/sedravasql/commit/a98e709cc591057298818d0972c12cf020054295) | B31, 81 тест, Clippy PASS; не подключено к SQL |

### Что изменилось после выпуска

- B26: повторное использование проверенной схемы при чтении; категория 1,68×, агрегация 1,85× по медианам отдельного опыта.
- B27: прямое декодирование JSON; кеш строк отклонён. Выборка без индекса 2,53×, агрегация 2,04× в серии испытаний.
- B28: диапазонный поиск в BTreeMap журнала; на 2048 ключах выборка 1/8/32 строк — 138,4×/89,7×/37,8× против принудительного полного сканирования (эквивалентный запрос с дополнительным условием). Дисковый B25 не принят как SQL backend.
- B29: отдельный бинарный COW B+Tree, 4 КиБ страницы, прямые адреса, кеш до 64 узлов, атомарные пакеты до 16 операций.
- B30: независимая уплотнённая копия, ревизии и tombstones сохранены. Испытано 20 480 ключей; финальная фаза 50,79 → 10,94 МБ.
- B31: UTF-8 значения до 64 КиБ (inline до 256 байт), проверяемые overflow-цепочки; 960 ключей, 16,08 МБ полезных данных, уплотнение 24,76 → 18,87 МБ. Лимит полезных данных compact_copy 32 МиБ проверен с превышением на один байт.

Эти измерения сделаны на общем VDS, относятся к отдельным нагрузкам и не доказывают универсального ускорения или превосходства над SQLite. Тесты аварийного завершения процесса не подтверждают устойчивость к физическому отключению питания. Публичные архивы не содержат последующих изменений B26–B31; номера этапов не являются версиями выпуска.

### Следующая работа

B32 — безопасное повторное использование недостижимых страниц с проверкой карты владения и границ публикации поколения; затем долговременные квитанции, миграция и SQL-интеграция после отдельных проверок. Пока нет in-place vacuum, BLOB, автоматического переключения уплотнённой пары файлов, промышленной надёжности или многопользовательского SQL-сервера. Основной NativeLog остаётся источником SQL-данных. Не использовать ценные данные.

**Отчёты и исходные измерения:** [B26](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B26_PERFORMANCE.ru.md) · [B27](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B27_PERFORMANCE.ru.md) · [B28](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B28_ORDERED_RANGE.ru.md) · [B28-A](https://github.com/VasiliiBabkin/sedravasql/blob/research/b28-tree-sql/docs/NATIVE_SQL_B28_TREE_EXPERIMENT.ru.md) · [B29](https://github.com/VasiliiBabkin/sedravasql/blob/research/b29-cow-tree/docs/NATIVE_COW_B29.ru.md) · [B30](https://github.com/VasiliiBabkin/sedravasql/blob/research/b30-compact/docs/NATIVE_COW_B30.ru.md) · [B31](https://github.com/VasiliiBabkin/sedravasql/blob/research/b31-overflow/docs/NATIVE_COW_B31.ru.md).
