# Sedrava brand assets / Бренд-ассеты Sedrava

`sedrava-logo-primary.png` is the approved, unmodified PNG master (1269 × 1239, RGBA).
Исходный утверждённый PNG сохранён без изменения байтов.

Master SHA-256: `da9c46be34b8a14d5fb262d3ae1bb18c4ff4b50badd8541837d2d8128d1e1fbb`.

The 32, 48, 180, 192 and 512 px PNGs preserve the entire source canvas, scaled with Lanczos and centered on transparent square canvases. ICO contains 16, 32 and 48 px images. The 1200 × 630 social image composites the unchanged mark onto #151122. No shapes, colors or highlights were redrawn. `SHA256SUMS` records the binary assets.

PNG-иконки сохраняют весь исходный холст и пропорции; квадратные поля прозрачны. OG-изображение использует тёмный фон. Перерисовка, изменение градиентов и деформация знака не допускаются.

The same master is mirrored in sedrava (`assets/brand`) and sedrava-site (`public/brand`). When updating derivatives, verify the master checksum first. The website's Sedrava demo uses a byte-identical copy of the 512 px derivative.

These assets identify the Sedrava project. Existing project license and trademark terms continue to apply; this change grants no additional trademark rights. / Условия лицензии и использования товарного знака не изменяются.

Rebuild with Pillow installed: `python scripts/build_brand_assets.py assets/brand` from the language repository. The script rejects any other master checksum.
