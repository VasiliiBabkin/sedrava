# Офлайн-список задач (Sedrava 0.10.0)

Нужны Python 3.10+ и опубликованная Sedrava 0.10.0; исходники клонируются для файлов примеров:

```sh
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
python -m pip install '.[test]'
sedrava check examples/task_manager.sdr
sedrava test examples/task_manager.sdr
sedrava run examples/task_manager.sdr
sedrava run examples/task_manager.sdr --state-file build/tasks-state.json
sedrava build web examples/task_manager.sdr --output build/tasks-web/index.html
python -m http.server 8000 --directory build/tasks-web
```

Откройте http://localhost:8000. Введите название и нажмите «Добавить». Выберите
строку; «Выполнено» переключает статус, «Переименовать» использует текущее поле
названия, «Удалить» удаляет выбранный ID. После успешного добавления и изменения
название очищается. Пустое название и отсутствующий ID вызывают понятный отказ.
Пробелы не удаляются автоматически. Перезагрузка восстанавливает задачи; пустой
список показывает сообщение. Вместимость — 100 задач.

[Один исходный файл](../examples/task_manager.sdr) создаёт обе версии приложения.
Записи объявляются перед состояниями, поля имеют типы `int`, `bool`, `text`.
Вместимость списка обязательна. Операции возвращают новые значения; `require`
отклоняет действие, `get` ищет по ID. Индексация не поддерживается. Виджет
`list … select …` создаёт выбор строки. [Спецификация](RECORDS_COLLECTIONS_010.md)
описывает типы, границы, атомарность и формат сохранения.

Android: установите JDK 17, SDK 35 и Gradle 8.11.1 по [BUILD.md](BUILD.md):

```sh
sedrava build android examples/task_manager.sdr --output build/tasks-android
python scripts/prepare_records_android_tests.py build/tasks-android
gradle -p build/tasks-android --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
adb install -r build/tasks-android/app/build/outputs/apk/debug/app-debug.apk
```

Проверьте добавление, выбор, изменение, удаление, поворот и повторный запуск.
При пересоздании сохраняется принятое состояние целиком; между запусками — только
поля `persist`. Неверный черновик может не пережить пересоздание. Хранилище локальное,
без шифрования. Примеры Android получают независимые постоянные ID;
см. [настройку application ID](ANDROID_ID.ru.md). Несовместимое или повреждённое сохранение отклоняется
целиком с сообщением; миграции и частичное восстановление не поддерживаются.

Проверки: `python -m unittest discover -s tests -v` и
`python scripts/test_web_browser.py` (нужны Playwright и Chromium). JVM проверяет
сгенерированные функции состояния; эмулятор отдельно проверяет Compose. Фактические
результаты и ограничения указаны в [отчёте](COLLECTIONS_010_REPORT.md).
Это экспериментальная разработка 0.10, а не опубликованная версия.
