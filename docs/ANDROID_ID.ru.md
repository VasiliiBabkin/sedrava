# Идентификатор Android-приложения (Sedrava 0.10.0)

Название на экране и в лаунчере задаётся `app "…"`. Идентификатор установки — настройка сборки, не новая конструкция языка.

```sh
sedrava build android examples/task_manager_navigation.sdr --output build/daybook
sedrava build android examples/task_manager.sdr --output build/tasks
sedrava build android examples/task_manager_navigation.sdr --application-id com.example.daybook --output build/my-daybook
gradle -p build/daybook --no-daemon :app:assembleDebug :app:lintDebug
```

По умолчанию: `org.sedrava.app.a` и первые 32 шестнадцатеричных знака SHA-256 от **точного UTF-8 названия приложения**. Нет случайных значений, зависимости от пути, времени и содержимого действий. Регистр, пробелы, пунктуация и различные Unicode-последовательности различаются. Одинаковые названия намеренно дают один ID; для разных приложений с одинаковым названием задайте разные `--application-id`. 128-битный хеш устойчив к коллизиям, но не заменяет глобальный реестр.

Явный ID позволяет переименовывать приложение, сохраняя идентичность. Допустимы два и более сегмента через точку, только строчные ASCII-буквы, цифры и `_`; каждый сегмент начинается с буквы. Общая длина до 255 символов; ключевые слова Java/Kotlin запрещены. Флаг доступен только для `build android`. Ошибка отклоняется до создания проекта. В Python: `android_codegen_v03.generate(source, output, application_id="com.example.daybook")`.

Application ID, namespace Gradle и Kotlin package совпадают. Файл `sedrava-android.json` содержит итоговые настройки, пути исходников соответствуют пакету. Тесты и проверка разрешений используют этот файл. Каталог другого приложения повторно использовать нельзя. Старый проект без метаданных пересоздайте в новом каталоге из `.sdr`.

Android хранит данные отдельно по ID. Обновление сохраняет их при прежнем ID, том же сертификате подписи и совместимой схеме; Android также проверяет versionCode. В этом RC используется тестовый `versionCode=10001` вместо прежнего 1, `versionName=0.10.0rc1`; это не production-стратегия версий приложения. `adb install -r` проверяет повторную debug-установку. Debug-ключ на другом компьютере может отличаться; для распространения нужна собственная стратегия подписи и версий. Смена ID создаёт отдельное приложение без переноса данных. Для обновления прежнего экспериментального приложения можно явно сохранить `--application-id org.sedrava.generated` и прежнюю подпись; не используйте этот ID для нескольких приложений.

Название кодируется строковым ресурсом Android: Unicode, `@`, `?`, кавычки и переводы строк остаются текстом. Дополнительные разрешения не нужны. Web хранит данные по пути URL и названию; перемещение или переименование HTML не переносит сохранение автоматически.

```sh
python -c "import json; print(json.load(open('build/daybook/sedrava-android.json'))['application_id'])"
adb install -r build/daybook/app/build/outputs/apk/debug/app-debug.apk
# Вместо PACKAGE подставьте выведенный идентификатор:
adb shell am start -n PACKAGE/.MainActivity
```

Нет миграций схемы, шифрования, release-подписи, Gradle wrapper и произвольного управления темой/вёрсткой. [English](ANDROID_ID.en.md).
