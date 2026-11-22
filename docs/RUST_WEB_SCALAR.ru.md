# Нативная генерация Web-приложений Sedrava (эксперимент)

**Это не стабильный релиз и пока не доказательство полной совместимости
с Python 0.11.** Название файла документа историческое: первые эксперименты
были ограничены скалярным Web.

В Rust создан самостоятельный генератор автономного HTML/JavaScript
для режима app. Python не используется для генерации.

## Функции, прошедшие проверку на примерах

- typed int32/bool/text, checked overflow, Unicode text limits;
- атомарные действия, require, if, правила, derive и ввод;
- чистые функции, даты и стандартная библиотека;
- типизированные записи, ограниченные коллекции, стабильные ID;
- append/get/has/update/remove/count/next_id, filter/map/find/any/all/sort/sum;
- форма с выбором строки и редактированием данных;
- несколько экранов, guarded navigation, back/pop, связанные действия;
- browser storage для persist: схема 1, подпись типа, проверка данных,
  отказ от перезаписи повреждённого JSON и обнаруженного внешнего изменения;
- защита от HTML/script injection через экранирование текстов и литералов.

Проверочные программы:

    examples/counter.sdr
    examples/reference_09.sdr
    examples/task_manager.sdr
    examples/task_manager_navigation.sdr
    tests/rust_cases/native_web_functions.sdr
    tests/rust_cases/native_web_queries.sdr

## Как проверить

Из корня репозитория:

    cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
    ./rust/target/debug/sedrava-native build web examples/task_manager_navigation.sdr --output build/native-app/index.html
    python3 scripts/verify_native_web.py

Скрипт использует Node.js и имитацию DOM. Он сравнивает часть поведения
генерируемого JavaScript с фактическими результатами Rust и Python;
в частности, проверяет коллекционные запросы и восстановление сохранений.
Это **не полноценный Chromium/Firefox/WebKit E2E**.

## Ограничения и гарантии

- Режимы site и webapp со сложными компонентами, layout, темами,
  stylesheet, assets, HTTP/API и сервисами **ещё не перенесены**.
- Нативный Android Compose-генератор пока отсутствует.
- JS localStorage не обеспечивает атомарную операцию compare-and-swap между
  несколькими вкладками. Реализована проверка обнаруженного изменения
  перед записью, а не гарантия одновременной транзакции.
- Гарантии сохранности при потере питания и кросс-браузерная совместимость
  не проверены; хранение браузером не зашифровано.
- Формат IR экспериментальный; источник ошибок не имеет полной карты
  выражений и позиций.
- Нет внешнего npm/Playwright релизного сертификата. Результаты касаются
  конкретных тестовых программ и среды проверки.

Приоритет дальнейшего переноса: Site/WebApp и Android/Host APIs,
после этого комплексные реальные браузерные/device испытания и
переключение только при прохождении критерия задачи
[№65](https://github.com/VasiliiBabkin/sedrava/issues/65).
