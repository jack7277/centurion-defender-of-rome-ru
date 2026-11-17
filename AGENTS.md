# Centurion: Defender of Rome — русификация

## ГЛАВНАЯ ДИРЕКТИВА: ЭКОНОМИЯ ТОКЕНОВ
- Отвечай коротко, без воды. Не пересказывай очевидное.
- Не читай файлы целиком без нужды — точечные offset'ы, grep, head.
- Не гоняй длинные прогоны «на всякий случай»; лимитируй шаги/время.
- Не дублируй в ответе то, что уже записано в файлы проекта.
- Состояние работы — в файлах (см. ниже), а не в чате: перед ответом пиши важное в STATUS.md, читай его вместо переспрашивания.
- Временные файлы (скриншоты тестов, логи, дампы) — только в %TEMP% (скриншоты: %TEMP%\centurion_screens). Не оставляй их в проекте.

## Ключевые пути
- Игра: `Centurion_Defender_of_Rome/` (оригиналы — `analysis/orig/`)
- Работа: `analysis/` — textool.py (тексты), font_ru.py (шрифт), runner.py (эмулятор 8086), emu_reloc.py (релоки LZEXE), run_ru_test.py (DOSBox-скриншоты)
- Доки: `analysis/FORMATS.md`, `analysis/PLAN_string_limits.md`, `analysis/STATUS.md`

## Формат движка (установлено)
- Ядро CENTURIO.EXE (LZEXE) → unpacked-образ `analysis/CENTURIO.unpacked.bin`; пересборка EXE: релоки `analysis/relocs.json` (56 шт), скрипт-сборщик выдаёт `analysis/CENTURIO.new.exe`.
- Текстовый движок ядра: draw_string 0x89C8 / measure 0x8C84 / draw_char 0x8D82; фильтр `cmp al,0x20; jl` (знаковый) режет байты ≥0x80 → патч jl→jb @0x8CA1 и @0x8A8D.
- Шрифт OVL0.OVL: ширины 0x1509C, y-offsets 0x150FC, битмапы 8x8 1bpp 0x1515C (96 глифов 0x20-0x7F), дескриптор 0x1545C (widths/yoffs/bitmaps ptrs + h8/sp3/sp1/sh0).
- OVL0: DGROUP грузится с офсета 0xB400 в ds:0 (0xC410 байт), BSS ds 0xA64C-0xC410, далее стек.
