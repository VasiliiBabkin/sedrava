> **Historical procedure (completed 31 October 2026).** Sedrava 0.10.0 is published on [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [PyPI](https://pypi.org/project/sedrava/0.10.0/), via [successful publishing workflow](https://github.com/VasiliiBabkin/sedrava/actions/runs/41237159326). Steps below record the pre-release procedure, not unfinished obligations. Final 0.10 physical-device acceptance remains unconfirmed.

# Sedrava 0.10.0 — публикация / Owner checklist

**Подготовка не означает выпуск. Не публиковать до выполнения всех ворот и разрешения владельца.**

1. Заполнить [физический протокол](PHYSICAL_DEVICE_010.md): реальная дата, APK, SHA, сценарии, наблюдения. Если полного прогона нет, явно ограничить поддержку Android эмулятором.
2. Утвердить период наблюдения RC2. На *финальном SHA* проверить [все ворота](STABLE_RELEASE_GATES_010.md), CI Python/JS/Kotlin/Chromium/Android, wheel/sdist, регрессии, отсутствие P0/P1.
3. Проверить и влить PR; исторические rc1/rc2 теги не менять.
4. В GitHub Settings → Environments настроить `pypi` и при необходимости `testpypi`. Рекомендуется подтверждение от владельца перед публикацией через `pypi`, а также защита релизных тегов.
5. Если проект `sedrava` ещё **не существует** на PyPI, в [настройках аккаунта PyPI → Publishing](https://pypi.org/manage/account/publishing/) создать **Add a new pending publisher**. Если уже существует и принадлежит вам — Project → Manage → Publishing → Add a new publisher.
   - PyPI project name: `sedrava`
   - GitHub owner: `VasiliiBabkin`
   - GitHub repository: `sedrava`
   - Workflow filename: `publish-pypi.yml`
   - Environment name: `pypi`
6. При желании повторить отдельно в [TestPyPI](https://test.pypi.org/manage/account/publishing/) с environment `testpypi`. Ручной запуск workflow разрешает **только** TestPyPI.
7. После явного разрешения на выпуск создать тег на проверенном коммите и отправить:
   ```sh
   git tag -a v0.10.0 -m "Sedrava 0.10.0"
   git push origin v0.10.0
   ```
   Только точный тег `v0.10.0` запускает автоматическую публикацию в основной PyPI.
8. Проверить Actions и [PyPI](https://pypi.org/project/sedrava/0.10.0/). В чистом `venv` вне исходного репозитория проверить `python -m pip install sedrava==0.10.0` и `sedrava --version`.
9. Создать обычный (не prerelease) GitHub Release по **тому же** тегу, используя [release notes](RELEASE_NOTES_0_10_0.md).

Токены вручную создавать и передавать не требуется: используется OIDC Trusted Publishing.
