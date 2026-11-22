# Rust → Kotlin/Android: типизированные Error, Result и match

Экспериментальное расширение генератора Android для номинальных ошибок
Rust Core из [PR #78](https://github.com/VasiliiBabkin/sedrava/pull/78).
Полная совместимость с неизданной Python 0.12 не является целью.
Существующие программы без типизированных ошибок должны работать как прежде.

## Контракт

- `SdrError(family,id,variant,fields)` — неизменяемое значение с проверкой
  номинального семейства, стабильного ID и точного payload по схеме.
- `SdrResult.Success(value)` / `SdrResult.Failure(error)` — типизированные
  варианты результата, не исключения JVM.
- `checkValue` проверяет `SdrType.Error` и `SdrType.Result`, включая
  ограничения int/text/bool для полей.
- `Ok` / `Err`, `result_ok`, `result_or`, `error_id` компилируются Rust
  без запуска Python, динамического `eval` или рефлексии.
- `match` вычисляет выражение ровно один раз, связывает immutable поля
  локально в выбранной ветви, допускает aliases и финальный `Err(error)`.
  Неожиданные значения вызывают отказ.
- Kotlin `transition` работает с копией состояния: переполнение,
  неверный payload и нарушение правила не публикуют промежуточное состояние.

Диагностическое `encodeJson(resolve(state))` для эфемерных Result/Error
должно соответствовать Rust. Обычный persistent snapshot не хранит
ошибки. Нет wire-декодера для пользовательских ошибок.

## Пример

```sh
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
./rust/target/debug/sedrava-native test examples/native_typed_errors_a1/main.sdr
./rust/target/debug/sedrava-native build android \
  examples/native_typed_errors_a1/main.sdr \
  --output build/typed-android \
  --application-id org.sedrava.typed
```

Kotlin/JVM conformance:

```sh
python3 scripts/verify_native_android_typed_result.py --gradle /PATH/TO/gradle
```

APK (Android SDK 35, JDK 17, Gradle):

```sh
cd build/typed-android
gradle --no-daemon :app:assembleDebug
```

APK из экспериментальной ветки — тестовая, не опубликованный релиз.

## Не перенесено

Legacy `Result<T,Error>` и `try_*`-адаптеры, вложенные Result,
persistent Error/Result, импортные namespace aliases,
Host/Server typed adapters и полный набор исходных координат/бюджетов
Python 0.12. Kotlin/JVM не является проверкой на Android-устройстве;
`assembleDebug` доказывает сборку, но не корректность UI на устройстве.
Issue #65 остаётся открытой до всех финальных проверок.


### Импорт номинальных типов

Простой плоский import поддерживает error-семейства и функции из
локального модуля (пример:
`examples/native_typed_errors_modules/main.sdr`). Для импортированного
error обязательно задать явный `id` — это защищает от случайного
изменения идентичности при переносе файла. Полные alias/namespaces,
перекрытие имён и package-API 0.12 не реализованы.
