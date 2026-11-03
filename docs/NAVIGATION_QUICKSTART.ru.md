# Двухэкранный менеджер задач — Sedrava 0.10.0

Нужны Python 3.10+ и Sedrava 0.10.0. Файлы примеров запускаются из клона репозитория:

```sh
python -m pip install '.[test]'
sedrava check examples/task_manager_navigation.sdr
sedrava test examples/task_manager_navigation.sdr
sedrava run examples/task_manager_navigation.sdr
sedrava build web examples/task_manager_navigation.sdr --output build/navigation-web/index.html
python -m http.server 8000 --directory build/navigation-web
```

Откройте http://localhost:8000. Добавьте задачу, откройте карточку, измените название
и нажмите Save title. Переключите выполнение, вернитесь кнопкой приложения или Back
браузера. Forward открывает экран с актуальными общими данными, не отменяя правки.
Удаление убирает выбранный устойчивый ID и возвращает к списку. Отсутствующий ID,
переполнение и неверный ввод не применяют часть изменений. Поля новой задачи и
редактора — два отдельных текстовых состояния в исходном файле.

`screen` объявляет экран, `navigation: initial main` задаёт начальный экран.
`action open_details -> details using prepare_details` выполняет доменное действие
и переход атомарно. `action back -> pop` возвращает назад; в корне это успешная
операция без изменения стека. Охрана `screen details when chosen:` требует bool:
несуществующая выбранная запись не позволяет открыть подробности. Удаление записи
с активного экрана убирает недопустимые экраны со стека.
[Контракт и справочник синтаксиса](NAVIGATION_010_CONTRACT.md) задаёт точные правила.

`list tasks select selected open open_details title title status done` создаёт
карточки и объединяет выбор ID с переходом. Поле заголовка должно иметь тип text,
статуса выполнения — bool. `display` показывает скалярное выражение;
`input title label "Task title"` задаёт подпись редактора. JavaScript и Kotlin
автору приложения писать не нужно.

Перезагрузка браузера и холодный запуск Android открывают начальный экран,
восстанавливая только данные `persist`. История хранит экраны, а не снимки задач.
В корне Back браузера может покинуть страницу, системный Back Android передаётся
платформе. Поворот и пересоздание Activity сохраняют принятое состояние и стек
вместе. Неверный черновик может исчезнуть. При повторном открытии явное действие
`prepare_details` загружает сохранённое название; Save записывает его в запись.

Для Android установите JDK 17, SDK 35 и Gradle 8.11.1 по [BUILD.md](BUILD.md):

```sh
sedrava build android examples/task_manager_navigation.sdr --output build/navigation-android
python scripts/prepare_navigation_android_tests.py build/navigation-android
python scripts/prepare_navigation_ui_tests.py build/navigation-android
gradle -p build/navigation-android --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
# При запущенном эмуляторе:
bash scripts/test_navigation_emulator.sh
```

Скрипты добавляют только тесты и зависимости тестовой сборки. Сценарий проверяет
системный Back, поворот, пересоздание, остановку процесса и новый запуск, настоящий
SharedPreferences и восстановленный интерфейс. Примеры имеют независимые постоянные
Android ID; см. [настройки сборки](ANDROID_ID.ru.md). Миграций и шифрования нет.

Регрессия: `python -m unittest discover -s tests -v`; браузер:
`python scripts/test_web_browser.py` (Playwright/Chromium). Фактические проверки
JVM, эмулятора и устройства разделены в [отчёте](NAVIGATION_010_REPORT.md).
Это экспериментальная разработка, а не выпуск 0.10.
