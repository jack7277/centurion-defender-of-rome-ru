# Centurion: Defender of Rome — русификация

## ГЛАВНАЯ ДИРЕКТИВА: ЭКОНОМИЯ ТОКЕНОВ
- Отвечай коротко, без воды. Не пересказывай очевидное.
- Не читай файлы целиком без нужды — точечные offset'ы, grep, head.
- Не гоняй длинные прогоны «на всякий случай»; лимитируй шаги/время.
- Не дублируй в ответе то, что уже записано в файлы проекта.
- Состояние работы — в файлах (см. ниже), а не в чате: перед ответом пиши важное в STATUS.md, читай его вместо переспрашивания.
- Временные файлы (скриншоты тестов, логи, дампы) — только в %TEMP% (скриншоты: %TEMP%\centurion_screens). Не оставляй их в проекте.

## GIT: КОММИТЬ И ПУШИТЬ КАЖДОЕ ИЗМЕНЕНИЕ
- Репо: https://github.com/jack7277/centurion-defender-of-rome-ru (origin, ветка main).
- После ЛЮБОГО изменения файлов проекта — сразу `git add` + `git commit` + `git push origin main`.
- Сообщение коммита — по-русски, с подписями: ЧТО изменено, ГДЕ (файл/адрес), ЗАЧЕМ (какой баг/экран чинит). Пример: «build_ru.py: пятый far-call @0x8AA0 в пещеру C1 — чинит битые буквы в строковом цикле боя».
- Одно логическое изменение = один коммит; не копи пачки правок.
- Перед коммитом проверяй `git status` — темпы и копирайт-файлы (.gitignore) не коммитить.

## Ключевые пути
- Игра: `Centurion_Defender_of_Rome/` (оригиналы — `analysis/orig/`)
- Работа: `analysis/` — textool.py (тексты), font_ru.py (шрифт), runner.py (эмулятор 8086), emu_reloc.py (релоки LZEXE), run_ru_test.py (DOSBox-скриншоты)
- Доки: `analysis/FORMATS.md`, `analysis/PLAN_string_limits.md`, `analysis/STATUS.md`

## Формат движка (установлено)
- Ядро CENTURIO.EXE (LZEXE) → unpacked-образ `analysis/CENTURIO.unpacked.bin`; пересборка EXE: релоки `analysis/relocs.json` (56 шт), скрипт-сборщик выдаёт `analysis/CENTURIO.new.exe`.
- Текстовый движок ядра: draw_string 0x89C8 / measure 0x8C84 / draw_char 0x8D82; фильтр `cmp al,0x20; jl` (знаковый) режет байты ≥0x80 → патч jl→jb @0x8CA1 и @0x8A8D.
- Шрифт OVL0.OVL: ширины 0x1509C, y-offsets 0x150FC, битмапы 8x8 1bpp 0x1515C (96 глифов 0x20-0x7F), дескриптор 0x1545C (widths/yoffs/bitmaps ptrs + h8/sp3/sp1/sh0).
- OVL0: DGROUP грузится с офсета 0xB400 в ds:0 (0xC410 байт), BSS ds 0xA64C-0xC410, далее стек.
