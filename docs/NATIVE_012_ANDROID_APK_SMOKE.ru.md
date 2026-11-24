> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava Native 0.12.0-alpha.1 — тестовое Android APK

Дата: 23 ноября 2026. Платформа сборки: VDS Ubuntu Linux x86_64.

## Что сделано

Нативный компилятор Sedrava 0.12.0-alpha.1 (Rust) успешно сгенерировал
Android-приложение из \`examples/android_native_test.sdr\`. Исходник —
настоящая программа Sedrava, без вручную написанного Java/Kotlin UI.
Android-проект затем собран Gradle 8.11.1 и Android Gradle Plugin 8.9.2,
Kotlin Android 2.0.21, Android SDK Platform 35 / Build Tools 35.0.0,
Java 17.

Выходной APK: \`Sedrava-Native-Test-0.12.0-alpha.1-debug.apk\`.
Сохраняется на VDS в
\`~/.sedrava-dev/releases/0.12.0-alpha.1/android/\`.
Бинарный APK **не коммитится** в GitHub. Гарантированное
воспроизведение побайтно не обещается: APK подписан тестовым
сертификатом конкретной среды.

SHA-256 тестового APK (сборка VDS 2026-11-23):

    e21d2a04f9f790c61cd08910ea452431776f059d29638684cad63bda82af1d09

Размер: 8 772 887 байт. ID: ru.ladokod.sedrava.native012test.
Название на экране: «Проверка Sedrava».
minSdk 26 (Android 8.0), targetSdk 35 (Android 15).

В APK есть штатное внутреннее AndroidX-разрешение
\`DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION\`; опасных системных
разрешений приложение не запрашивает.

## Повторение сборки на VDS

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"

    "$CARGO_TARGET_DIR/release/sedrava-native" check examples/android_native_test.sdr
    "$CARGO_TARGET_DIR/release/sedrava-native" test examples/android_native_test.sdr

    "$CARGO_TARGET_DIR/release/sedrava-native" build android \
      examples/android_native_test.sdr \
      --output "$HOME/.sedrava-dev/android-test/new-phone-build" \
      --application-id ru.ladokod.sedrava.native012test

    cd "$HOME/.sedrava-dev/android-test/new-phone-build"
    printf 'sdk.dir=%s\n' "$ANDROID_HOME" > local.properties
    "$HOME/.cache/sedrava-rust-verify/tooling/gradle-8.11.1/bin/gradle" \
       --no-daemon --console=plain :app:assembleDebug

    cd "$HOME/.sedrava-dev/sedrava"
    python3 scripts/verify_native_android_apk.py \
      --apk "$HOME/.sedrava-dev/android-test/new-phone-build/app/build/outputs/apk/debug/app-debug.apk" \
      --sdk "$ANDROID_HOME"

Все каталоги SDK, Gradle и Cargo сохраняются для следующих сборок.
Не использовать GitHub Actions ради этих проверок.

## Что проверить на телефоне

1. Установить отладочный APK и открыть «Проверка Sedrava».
2. Добавить две задачи, убедиться, что обе появились.
3. Открыть одну задачу, переименовать и сохранить.
4. Отметить выполненной, затем снова изменить статус.
5. Вернуться к списку и удалить одну задачу.
6. Полностью закрыть приложение и открыть снова — оставшиеся
   задачи и статусы должны сохраниться.
7. По возможности повернуть экран, повторить операции с русскими
   и латинскими символами. Не использовать важные личные данные.

Нужно сообщить результат по каждому шагу (PASS/FAIL), а при ошибке
приложить текст ошибки, скриншот или воспроизведение. Для APK,
собранного на другой машине с другой подписью, Android может
отказать в обновлении поверх этой тестовой сборки. В таком случае
потребуется согласованная схема подписи и обновления.

**Текущие границы проверки:** подтверждена настоящая сборка APK
\`assembleDebug\`, анализ APK, SHA, подпись и отсутствие опасных
разрешений. Установка и исполнение на физическом телефоне,
обновление/откат, долговременное хранение и разные Android версии
**пока не проверены**. Это не production-release и не Android
совместимость всей Sedrava 0.12.
