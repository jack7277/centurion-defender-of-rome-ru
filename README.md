# Centurion: Defender of Rome — русификатор

Инструменты и ресурсы для перевода игры **Centurion: Defender of Rome** (1990, DOS) на русский язык: кириллический шрифт, патчи текстового движка ядра, извлечение/сборка текстов, GUI-редактор шрифта и прогон тестов в DOSBox.

## Структура

- `texts.txt` — все строки игры с индексами и лимитами длины (`max=` в байтах cp866); редактируется вручную
- `analysis/` — инструменты:
  - `build_ru.py` — **главная сборка**: тексты + кириллица («ds-pocket») + пересборка EXE, результат кладётся в `Centurion_Defender_of_Rome/`
  - `textool.py` — извлечение/сборка строк OVL0.OVL
  - `apply_translations.py` + `translations.py` — подстановка переводов в texts.txt с проверкой лимитов
  - `font_editor.py` — GUI-редактор шрифта с кнопкой пересборки (`FONTEDIT.BAT`)
  - `run_ru_test.py` — прогон сборки в DOSBox со скриншотами (в `%TEMP%\centurion_screens`)
  - `emu_reloc.py` — распаковка LZEXE-ядра и снятие релокаций
  - `cbm_decode.py`, `sprite_decode.py`, `gamedec.py` — декодеры графики
  - `STATUS.md`, `FORMATS.md`, `PLAN_string_limits.md` — документация по форматам и ходу работ
- `decoded/FONT_8x8_ru.bin` — кириллический шрифт (8x8, 1bpp)
- Батники: `build_texts.bat`, `dump_texts.bat`, `restore_texts.bat`, `FONTEDIT.BAT`

## Сборка с нуля

Файлы игры не входят в репозиторий (копирайт). Нужна своя копия игры:

1. Положить игру в `Centurion_Defender_of_Rome/`, оригиналы `CENTURIO.EXE` и `OVL0.OVL` — в `analysis/orig/`.
2. Распаковать ядро: `python emu_reloc.py` (в каталоге с `CENTURIO.EXE`) → `unpacked_emu.bin` + `relocs.json`; затем первые 45320 байт `unpacked_emu.bin` сохранить как `analysis/CENTURIO.unpacked.bin`.
3. Отредактировать `texts.txt` (переводы), при необходимости шрифт — `FONTEDIT.BAT`.
4. `cd analysis && python build_ru.py` — собрать русскую версию в каталог игры.
5. `python run_ru_test.py N` — прогнать в DOSBox и снять N скриншотов.

Технические детали (схема «ds-pocket», адреса патчей, форматы ресурсов) — в `analysis/STATUS.md` и `analysis/FORMATS.md`.
