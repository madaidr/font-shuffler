import random
import argparse
import copy
import glob
import os
import datetime
from fontTools.ttLib import TTFont


def get_common_unicodes(fonts):
    cmaps = [font.getBestCmap() for font in fonts]
    common = set(cmaps[0].keys())
    for cmap in cmaps[1:]:
        common.intersection_update(cmap.keys())
    return common


def scale_glyph(glyph, scale):
    if glyph.numberOfContours < 0:
        return glyph
    new_glyph = copy.deepcopy(glyph)
    if hasattr(new_glyph, 'coordinates') and new_glyph.coordinates is not None:
        new_glyph.coordinates *= scale
    return new_glyph


def copy_glyph_data(source_font, source_glyph_name, target_glyph_name, target_font):
    if source_glyph_name not in source_font['glyf']:
        return False
    source_glyph = source_font['glyf'][source_glyph_name]
    if source_glyph.numberOfContours < 0:
        return False
    target_upm = target_font['head'].unitsPerEm
    source_upm = source_font['head'].unitsPerEm
    scale = target_upm / source_upm

    scaled_glyph = scale_glyph(source_glyph, scale)
    target_font['glyf'][target_glyph_name] = scaled_glyph

    if source_glyph_name in source_font['hmtx'].metrics:
        advance, side_bearing = source_font['hmtx'][source_glyph_name]
        target_font['hmtx'][target_glyph_name] = (round(advance * scale), round(side_bearing * scale))
    if 'vmtx' in source_font and source_glyph_name in source_font['vmtx'].metrics:
        advance, side_bearing = source_font['vmtx'][source_glyph_name]
        target_font['vmtx'][target_glyph_name] = (round(advance * scale), round(side_bearing * scale))
    return True


def update_metadata(font, family_name=None, version_string=None, copyright_string=None,
                    add_suffix=True, source_files=None):
    """
    Обновляет название, версию, авторские права, описание и устанавливает пустую организацию.
    source_files – список путей к исходным шрифтам (для поля Description).
    """
    name_table = font['name']
    current_year = datetime.datetime.now().year
    suffix = f" (Mixed {current_year})" if add_suffix else ""

    def get_existing(name_id):
        for record in name_table.names:
            if record.nameID == name_id:
                return record.toUnicode()
        return ""

    # Copyright
    if copyright_string is not None:
        new_copyright = copyright_string
    else:
        existing = get_existing(0)
        new_copyright = existing + suffix if add_suffix and existing else existing or f"Mixed Font {current_year}"

    # Family
    if family_name is not None:
        new_family = family_name + suffix
    else:
        existing = get_existing(1)
        new_family = existing + suffix if add_suffix and existing else existing or f"MixedFont{current_year}"

    # Version
    if version_string is not None:
        new_version = version_string
    else:
        existing = get_existing(5)
        new_version = existing if existing else "Version 1.0"

    # Full name и PostScript name
    new_full = f"{new_family} Regular"
    new_ps = new_family.replace(" ", "") + "-Regular"

    # Description (nameID=10) – список исходных шрифтов
    if source_files:
        # Берём только имена файлов (без путей) для краткости
        base_names = [os.path.basename(f) for f in source_files]
        description = "Mixed font generated from: " + ", ".join(base_names)
    else:
        description = "Mixed font"

    for record in name_table.names:
        if record.nameID == 0:
            record.string = new_copyright.encode(record.getEncoding())
        elif record.nameID == 1:
            record.string = new_family.encode(record.getEncoding())
        elif record.nameID == 4:
            record.string = new_full.encode(record.getEncoding())
        elif record.nameID == 5:
            record.string = new_version.encode(record.getEncoding())
        elif record.nameID == 6:
            record.string = new_ps.encode(record.getEncoding())

    # Установка Description (nameID=10) – удаляем старые и добавляем новую запись
    for record in name_table.names[:]:
        if record.nameID == 10:
            name_table.names.remove(record)
    name_table.setName(description, 10, 3, 1, 0x409)  # Windows, Unicode, английский

    # Установка пустой организации (Manufacturer, nameID=8)
    for record in name_table.names[:]:
        if record.nameID == 8:
            name_table.names.remove(record)
    name_table.setName("", 8, 3, 1, 0x409)

    # Обновление времени модификации
    head = font['head']
    now = datetime.datetime.now()
    epoch = datetime.datetime(1904, 1, 1)
    head.modified = int((now - epoch).total_seconds())


def main():
    parser = argparse.ArgumentParser(description="Перемешивает символы из TTF-шрифтов в папке")
    parser.add_argument('--folder', default='.', help='Папка с TTF')
    parser.add_argument('--output', default='mixed_font.ttf', help='Выходной файл')
    parser.add_argument('--family', default='Regular', help='Название семейства')
    parser.add_argument('--version', default='1', help='Версия')
    parser.add_argument('--copyright', default='mit', help='Авторские права')
    parser.add_argument('--organization', default='', help='Игнорируется (организация всегда пустая)')
    parser.add_argument('--no-suffix', action='store_true', help='Не добавлять суффикс')
    args = parser.parse_args()

    ttf_files = glob.glob(os.path.join(args.folder, '*.ttf'))
    if len(ttf_files) < 2:
        print(f"Ошибка: найдено {len(ttf_files)} TTF-файлов, нужно минимум 2.")
        return

    print(f"Найдено шрифтов: {len(ttf_files)}")
    for f in ttf_files:
        print(f"  {f}")

    fonts = [TTFont(f) for f in ttf_files]
    base_font = fonts[0]
    new_font = copy.deepcopy(base_font)

    common_unicodes = get_common_unicodes(fonts)
    print(f"Общих символов: {len(common_unicodes)}")

    base_cmap = base_font.getBestCmap()
    for uni in common_unicodes:
        target_name = base_cmap.get(uni)
        if not target_name:
            continue
        src_font = random.choice(fonts)
        src_cmap = src_font.getBestCmap()
        src_name = src_cmap.get(uni)
        if not src_name:
            continue
        if copy_glyph_data(src_font, src_name, target_name, new_font):
            print(f"Скопирован U+{uni:04X} из '{src_name}' → '{target_name}'")
        else:
            print(f"Пропущен составной U+{uni:04X}")

    print("Обновление метаданных...")
    update_metadata(new_font,
                    family_name=args.family,
                    version_string=args.version,
                    copyright_string=args.copyright,
                    add_suffix=not args.no_suffix,
                    source_files=ttf_files)   # передаём список исходников

    print(f"Сохранение в {args.output}...")
    new_font.save(args.output)

    # --- Создание текстового файла со списком использованных шрифтов ---
    sources_file = os.path.splitext(args.output)[0] + "_sources.txt"
    with open(sources_file, 'w', encoding='utf-8') as f:
        f.write("Source fonts used to generate this mixed font:\n")
        for path in ttf_files:
            f.write(path + "\n")
    print(f"Список исходных шрифтов сохранен в {sources_file}")

    print("Готово!")


if __name__ == '__main__':
    main()