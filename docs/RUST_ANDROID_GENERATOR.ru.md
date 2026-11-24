> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Нативный Android-генератор Sedrava

Нативный генератор создаёт приложение Kotlin и Jetpack Compose из
поддерживаемого Rust app-mode. Разбор исходника, проверка типов и генерация
выполняются Rust. APK выполняет сгенерированную логику локально.
Python 0.11 остаётся основным компилятором и эталоном сравнения.

## Покрытие

- Скалярные и вычисляемые состояния, типизированные записи, bounded
  collections, устойчивые ID, чистые функции, запросы к коллекциям и
  поддержанная Rust stdlib.
- Проверяемая int32-арифметика, лимиты Unicode, `require` и `rule`.
  Действия выполняются над кандидатом. При ошибке состояние и стек
  экранов сохраняются.
- Экраны, guards, переходы с действием, pop и системный Back. Выбор
  записи и связанный переход выполняются атомарно. После изменения
  состояния экран с переставшим выполняться guard закрывается.
- Элементы app-mode `text`, `value`, `show`, `display`, `input`,
  `button` и `list` с выбором, заголовком, статусом или переходом.
  Поля принимают int/text, а bool-изменения выражаются действиями.
  Прокручиваемая компоновка ограничивает ширину на больших экранах.
  Заголовки, выделение строк и сообщения об ошибках имеют семантику
  доступности. Манифест приложения не запрашивает сетевых разрешений.

В модели Python 0.11 app-mode отсутствуют отдельный switch и формы
WebApp DSL. Этот генератор принимает app-mode. Site, WebApp и Host
используют отдельные режимы.

## Состояние и совместимость

Android хранит UTF-8 JSON schema-1 в приватном файле
`files/sedrava-state.json`. Формат использует ту же сигнатуру и поля,
что snapshot Python и Rust. Записываются только значения `persist`.
Проверяются дубли JSON-ключей, корректность Unicode и int32, глубина,
размер, типы, идентификаторы и правила приложения.

Запись выполняется вне главного потока через временный файл с
синхронизацией данных и атомарной заменой. Перед записью сверяется
последняя прочитанная версия. Повреждённое исходное сохранение
остаётся на диске. Приложение показывает ошибку и отклоняет изменение
сохраняемых значений. В модели один процесс-писатель. Долговечность при
потере питания и несколько независимых писателей требуют отдельной проверки.

Если нативного файла ещё нет, приложение читает прежние Android
`SharedPreferences("sedrava_state")`: у Python 0.11 это схема 1 для
записей и навигации либо типизированные scalar preference keys для
скалярной программы. Первый успешно сохранённый нативный переход
записывает schema-1, исходные preferences сохраняются. Для обновления
установленного приложения нужно сохранить Android application ID,
доступ к каталогу прежнего приложения и подпись APK.

Поворот и пересоздание Activity используют ViewModel. Для восстановления
вытесненной Activity Android Bundle хранит ограниченный полный snapshot
и стек экранов. Bundle применяется только при совпадении с текущими
сохранёнными значениями. При холодном старте восстанавливаются значения
`persist`, а навигация начинается с начального экрана.

## Воспроизведение в изолированном окружении

Нужны JDK 17, Gradle 8.11.1 и Android SDK с `platforms;android-35`,
`build-tools;35.0.0` и `platform-tools`. AGP 8.9.2, Kotlin 2.0.21 и
Compose BOM 2024.12.01 соответствуют существующему Android-проекту.

~~~sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo build --manifest-path rust/Cargo.toml --locked
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
python3 scripts/verify_native_android.py
python3 scripts/verify_native_android_kotlin.py --gradle "$(command -v gradle)"
./rust/target/debug/sedrava-native build android examples/task_manager_navigation.sdr \
  --output build/android-native-tasks --application-id org.sedrava.nativecheck.tasks
gradle -p build/android-native-tasks --no-daemon :app:assembleDebug :app:lintDebug
apk=build/android-native-tasks/app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose "$apk"
"$ANDROID_HOME/build-tools/35.0.0/aapt" dump badging "$apk"
~~~

`verify_native_android_kotlin.py` компилирует полученные Kotlin-файлы
модели, коллекций, навигации, snapshot и файлового хранилища на JVM без
подмены Android/Compose библиотек. Проверяются последовательность
переходов по Python-эталону, результаты запросов, повреждённые данные,
условия отклонения, миграция preferences и чтение Android snapshot
интерпретаторами Python и Rust. APK-сборка отдельно компилирует настоящую
Android/Compose часть.

Для независимой проверки на эмуляторе используйте новый тестовый AVD.
Установите APK через `adb install "$apk"`, запустите
`adb shell am start -n org.sedrava.nativecheck.tasks/.MainActivity`.
Добавьте две задачи, откройте первую, переименуйте её, смените статус,
поверните устройство и проверьте, что открыт тот же экран. Вернитесь
назад, удалите одну запись, остановите и снова запустите приложение.
Проверьте восстановление списка, отказ пустого названия и
`adb logcat -d -s AndroidRuntime`. Ни Gradle, ни JVM-сценарии сами
по себе не подтверждают эти действия на устройстве.

Полная матрица переноса остаётся в [карте миграции](RUST_FULL_MIGRATION.ru.md).
