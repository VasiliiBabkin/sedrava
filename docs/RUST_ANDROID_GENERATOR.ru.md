# Экспериментальная генерация Android на Rust

**Статус: частичный перенос, не готовый Android-релиз.**

Rust может самостоятельно создавать исходный проект Android с Jetpack Compose
для проверенного одноэкранного подмножества языка. Вызова Python-компилятора
внутри генератора нет. Действующий Python 0.11 остается основным для Android.

## Команда

Из корня клона Sedrava (после установки Rust/Cargo):

    cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
    ./rust/target/debug/sedrava-native build android \
      tests/rust_cases/native_android_scalar.sdr \
      --output build/native-android-preview \
      --application-id org.sedrava.demo

Каталог output должен быть **новым и несуществующим**: генератор не будет
перезаписывать ранее созданный проект. Вначале собираются все файлы
в отдельном временном каталоге, затем публикуется готовая структура.

Структура включает MainActivity.kt, AndroidManifest.xml, strings.xml,
Gradle settings/build, gradle.properties и sedrava-android.json. Метаданные
identity совместимы с Python-проверкой project_identity.

## Что поддерживается сейчас

- Скалярные state: int32, bool, text.
- derive, rule, action, require, if/else, let, проверка int32 overflow.
- Простые элементы text/value/show/button/input/display на одном экране.
- Генерация Kotlin/Compose-кода и валидного манифеста Android.
- Явное application-id с валидацией допустимого package ID; ресурсы и
  строки экранируются.

## Явно не поддерживается

- Android persist, сохранение/восстановление данных между запусками.
- Типизированные записи и коллекции, UI-списки и запросы к ним.
- Чистые функции и полноценная stdlib в Android-коде.
- Navigation/multi-screen, Site/WebApp и Host API.

Если исходник требует этих возможностей, Rust-генератор должен отказать,
а не незаметно исключить их из проекта.

## Проверки

    python3 scripts/verify_native_android.py

Проверяет, что два вызова генератора с одинаковыми параметрами дают
идентичные файлы, корректные XML, приложение с нужным package ID,
проверку ограничений, отказ от небезопасных ID и отказ от перезаписи.

При наличии Gradle 8.11.1 можно дополнительно выполнить:

    python3 scripts/verify_native_android_kotlin.py \
      --gradle /path/to/gradle

Этот тест использует **реальный Kotlin JVM compiler**, но вместо Android
и Compose использует локальные тестовые заглушки, чтобы проверить синтаксис
и переходы состояния. Такой тест **не равен Gradle Android build / APK**.

На первоначальном VDS проверено наличие Java 17; Android SDK, adb и
системный Gradle отсутствовали. Поэтому не заявляется успешная сборка
или установка APK на телефон, пока это не будет отдельно подтверждено.

Завершение переноса Android будет возможно только после расширения
генератора на все публичные элементы Sedrava, испытаний реального
Android Gradle Plugin, Gradle/Lint/JVM и установки APK на устройстве.

Общее состояние: [задача №65](https://github.com/VasiliiBabkin/sedrava/issues/65).
