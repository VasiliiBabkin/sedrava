# Sedrava 0.12.0-alpha.4 · платформа A39

Экспериментальная alpha для Linux x86-64 GNU (Ubuntu 24.04). SedravaSQL 0.1.0-alpha.2 и NativeLog 0.0.2 не изменились. [Декларация «Описал — получил»](DECLARATION.ru.md).

## Установка

Скачайте архив sedrava-platform-0.12.0-alpha.4-sql-0.1.0-alpha.2-linux-x86_64.tar.gz, install_platform_a39.sh и SHA256SUMS со страницы выпуска. Сверьте SHA-256 архива и установщика с опубликованными значениями из доверенного источника. Не используйте непроверенные архивы.

~~~sh
sha256sum -c SHA256SUMS
ARCHIVE=sedrava-platform-0.12.0-alpha.4-sql-0.1.0-alpha.2-linux-x86_64.tar.gz
HASH=$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)
sh install_platform_a39.sh "$ARCHIVE" "$HASH" "$HOME/sedrava-alpha4"
export PATH="$HOME/sedrava-alpha4/bin:$PATH"
sedrava --version
~~~

Для полной команды sha256sum -c скачайте все файлы, перечисленные в SHA256SUMS. Установка без sudo и Python/Rust, в новый каталог, существующий не перезаписывается. Контрольные суммы не являются цифровой подписью.

## Пример из комплекта

~~~sh
cp -r "$HOME/sedrava-alpha4/examples/service_complete" "$HOME/service-demo-alpha4"
cd "$HOME/service-demo-alpha4"
sedrava test
sedrava build
sedrava package --output "$HOME/service-demo-alpha4-package"
sedrava project verify-package "$HOME/service-demo-alpha4-package"
~~~

Здесь domain.sdr — единственное описание предметной области, sedrava-project.json — манифест. Генерируемые app.sdr, api.sdr, migrations.json и UI доступны для просмотра в build/<sha256>. Старый sedrava new NAME пока создаёт проект формата 1; не смешивайте форматы.

### Локальный сервер с отдельной тестовой БД

Для подготовки ключа воспользуйтесь OpenSSL (не зависимость runtime). Команды Bash; вводимый секрет не помещается в исходники. Используйте новый каталог, не существующую БД.

~~~sh
DATA="$HOME/service-demo-alpha4-data"
mkdir -m 700 "$DATA" || exit 1
umask 077
KEY=$(openssl rand -hex 32)
HASH=$(printf '%s' "$KEY" | sha256sum | cut -d ' ' -f 1)
printf '[{"id":"writer","sha256":"%s","role":"write"}]\n' "$HASH" > "$DATA/auth.json"
printf 'Ключ входа: %s\n' "$KEY"
unset KEY HASH
sedrava migrate --data "$DATA" --trusted --apply
sedrava serve --data "$DATA" --trusted --auth-file "$DATA/auth.json" --allow-write --port 8080
~~~

Откройте http://127.0.0.1:8080 на том же компьютере, войдите ключом. Создайте заказчика, объект, оборудование и заявку; укажите дату YYYY-MM-DD. Выберите заявку и текущую версию, введите ID события, комментарий, минуты и стоимость для записи работы. Загрузите историю и итоги, затем выполните переход. Открытые зависимые списки обновляются автоматически после подтверждения записи. Для следующего перехода выберите свежую версию.

## Границы

Не открывать порт наружу и не использовать реальные ценные данные. Нет промышленной многопользовательской эксплуатации. Базы A33–A37 несовместимы с семантической историей A38; перенос не реализован. Не удалять существующие данные. Формат 1 сохраняется; новый формат 2 не является Android-генератором. Проверки на Ubuntu x86-64, другие платформы не квалифицированы. История сортируется по ID, а не дате. Новые ID, даты, курсоры и первичная загрузка пока ручные. [Контракт A37](SERVICE_DOMAIN_A37.ru.md) · [Ревизия A38](QUALIFICATION_A38.ru.md).

## Выпуск подтверждён

28 ноября 2026 года опубликован alpha.4, точный тег a309e23580b15828447ef9a78d4beb98f07e82ec. [Загрузки](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.4/) · [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.4) · [Forgejo run 7](https://git.virtreal.ru/kontinentus/sedrava-ci/actions/runs/7) — SUCCESS. Архив 6172347 байт, SHA-256 984350bb3fc55a34a4a6a874ea1842dc8c63f9e253002f11172c374f195016b5. 92 Rust, 7 alpha gates, регрессия A16–A37, 90 direct HTTP +21 jsdom +34 Chromium в установленном комплекте, 6 негативных случаев установщика, детерминированная упаковка — PASS. 9 файлов загрузки проверены по HTTPS, 22 прежних файла сохранены. Протокол: evidence/a39-release-2026-11-28. Это документационное дополнение после публикации: тег и байты архива не меняются.
