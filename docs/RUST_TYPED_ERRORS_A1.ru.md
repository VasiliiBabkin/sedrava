> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Нативные типизированные ошибки и Result — Core + Web A1

Экспериментальный перенос **ограниченного подмножества** Core 0.12 из
[PR #56](https://github.com/VasiliiBabkin/sedrava/pull/56).
Это не стабильный релиз, не весь язык 0.12 и не Host/Server API.

Пример: `examples/native_typed_errors_a1/main.sdr`.

## Что поддерживается

```sedrava
error closed ArithmeticError id "example.ArithmeticError":
    IntOverflow:
        left: int
        right: int
    InvalidScalar:
        scalar: int
error open ReadError:
    NotFound:
        path: text
fn checked(x: int) -> Result<int, ArithmeticError> effects pure = Ok(x) if x < 100 else Err(ArithmeticError.IntOverflow(left=x, right=1))
```

Не более 16 семейств, 16 вариантов в каждом и 16 полей в варианте;
payload — только `int`, `text`, `bool`. Имена и стабильные ID валидируются,
повторы запрещены. ID по умолчанию — `entry.Name`, ID варианта —
`FamilyID.Variant`. Это идентичность ошибок, **не** внешний протокол.

`Ok(value)` и `Err(ErrorType.Variant(...))` принимаются только в
контексте `Result<int|text|bool, DeclaredError>`. Конструкторы требуют
точный набор именованных полей и проверяют их тип; вычисление полей идёт
в порядке декларации. Доступны `result_ok(result)`,
`result_or(result, fallback)` и `error_id(error)`.

```sedrava
action inspect:
    match checked(100):
        Ok(value):
            total = value
        Err(IntOverflow { left, right: addend }):
            total = left + addend
        Err(InvalidScalar { scalar }):
            total = scalar
```

`match` вычисляет subject ровно один раз. `Ok` обязателен; для `closed`
нужны все варианты либо достижимый общий `Err(error)`, а для `open` —
обязательный **последний** `Err(error)`. Повторы, недостижимые arms,
неизвестные варианты/поля и неразрешённые binders отклоняются.
Arm-bindings неизменяемы, ограничены телом arm. Ошибка исполнения
не публикует промежуточные изменения действия.

Диагностический JSON результатов вида
`{"code":"","error":{"id":"example.ArithmeticError.IntOverflow","variant":"IntOverflow","fields":{"left":100,"right":1}}}`
выводится через `run`, но **не является форматом хранения или wire schema**.
Старые persistent-состояния schema-1 не изменены.

## Поддержанные генераторы

- **Rust CLI:** `check`, `test`, `run` и `effects` на этом подмножестве
  выполняются без Python.
- **Web:** `build web` генерирует JS. Результаты сравнивались в Node mock DOM
  с Rust и эталоном Python 0.12; это **не** реальные Chrome/Firefox/WebKit.
- **Android:** `build android` генерирует Kotlin для типизированных
  Result/match; Kotlin/JVM и APK проверяются отдельно.
- Простые плоские импорты error-типов из локальных .sdr теперь доступны
  при явном стабильном id; import-alias, полное пространство имён и
  Site/WebApp с импортированными ошибками ещё не квалифицированы.

## Не реализовано

Непрозрачный старый `Result<T, Error>` и `try_add`/`try_chr`/`try_at`,
полные адаптеры, nested/error-as-success, коллекции или persistent-ошибки,
широкие пространства имён, транспортые декодеры и Android Compose
для `match`. Не доказана идентичность всех diagnostic codes/source spans,
бюджетов каждой ветви, всех import-путей и всех программ Python 0.12.

`Result` никогда не перехватывает `BudgetExceeded`, `PolicyViolation`,
`CapabilityDenied`, `CompilerError`, `InternalError` или переполнения
payload, которые остаются ошибками выполнения. Синтаксис не выдаёт
файловые/сетевые разрешения.

## Воспроизведение

```sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
./rust/target/debug/sedrava-native test examples/native_typed_errors_a1/main.sdr
python3 scripts/verify_native_typed_errors.py
```

Для сравнения с Python 0.12 распаковать исходники точного SHA
`06e4d435bbf168c5df64f6bcd73b54cba8797a64` из PR #56 и выполнить:

```sh
python3 scripts/verify_native_typed_errors.py --python-reference /PATH/TO/PYTHON_012
```

Набор сравнивает шесть последовательностей и 22 отрицательных программы,
полное диагностическое состояние и Web JS в Node mock DOM. Реальные браузеры,
физический Android и все сценарии отказа ФС остаются отдельными воротами.
Issue #65 остаётся открытым.
