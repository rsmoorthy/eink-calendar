from PIL import Image, ImageDraw, ImageFont
import sys

# TEXT = "கு"
TEXT = "1"

FONT_FILE = "NotoSansTamil-Regular.ttf"
FONT_SIZE = 32
if len(sys.argv) > 1:
    FONT_SIZE = int(sys.argv[1])

chars = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "கு", "க", "ற", "ள்"]

ascii_chars = []
for i in range(32, 126):
    ascii_chars.append(chr(i))

tamil_chars = [
    "அ",
    "ஆ",
    "இ",
    "ஈ",
    "உ",
    "ஊ",
    "எ",
    "ஏ",
    "ஐ",
    "ஒ",
    "ஓ",
    "ஔ",
    "க்",
    "ங்",
    "ச்",
    "ஞ்",
    "ட்",
    "ண்",
    "த்",
    "ந்",
    "ப்",
    "ம்",
    "ய்",
    "ர்",
    "ல்",
    "வ்",
    "ழ்",
    "ள்",
    "ற்",
    "ன்",
    "க",
    "கா",
    "கி",
    "கீ",
    "கு",
    "கூ",
    "கெ",
    "கே",
    "கை",
    "கொ",
    "கோ",
    "கௌ",
    "ங",
    "ஙா",
    "ஙி",
    "ஙீ",
    "ஙு",
    "ஙூ",
    "ஙெ",
    "ஙே",
    "ஙை",
    "ஙொ",
    "ஙோ",
    "ஙௌ",
    "ச",
    "சா",
    "சி",
    "சீ",
    "சு",
    "சூ",
    "செ",
    "சே",
    "சை",
    "சொ",
    "சோ",
    "சௌ",
    "ஞ",
    "ஞா",
    "ஞி",
    "ஞீ",
    "ஞு",
    "ஞூ",
    "ஞெ",
    "ஞே",
    "ஞை",
    "ஞொ",
    "ஞோ",
    "ஞௌ",
    "ட",
    "டா",
    "டி",
    "டீ",
    "டு",
    "டூ",
    "டெ",
    "டே",
    "டை",
    "டொ",
    "டோ",
    "டௌ",
    "ண",
    "ணா",
    "ணி",
    "ணீ",
    "ணு",
    "ணூ",
    "ணெ",
    "ணே",
    "ணை",
    "ணொ",
    "ணோ",
    "ணௌ",
    "த",
    "தா",
    "தி",
    "தீ",
    "து",
    "தூ",
    "தெ",
    "தே",
    "தை",
    "தொ",
    "தோ",
    "தௌ",
    "ந",
    "நா",
    "நி",
    "நீ",
    "நு",
    "நூ",
    "நெ",
    "நே",
    "நை",
    "நொ",
    "நோ",
    "நௌ",
    "ப",
    "பா",
    "பி",
    "பீ",
    "பு",
    "பூ",
    "பெ",
    "பே",
    "பை",
    "பொ",
    "போ",
    "பௌ",
    "ம",
    "மா",
    "மி",
    "மீ",
    "மு",
    "மூ",
    "மெ",
    "மே",
    "மை",
    "மொ",
    "மோ",
    "மௌ",
    "ய",
    "யா",
    "யி",
    "யீ",
    "யு",
    "யூ",
    "யெ",
    "யே",
    "யை",
    "யொ",
    "யோ",
    "யௌ",
    "ர",
    "ரா",
    "ரி",
    "ரீ",
    "ரு",
    "ரூ",
    "ரெ",
    "ரே",
    "ரை",
    "ரொ",
    "ரோ",
    "ரௌ",
    "ல",
    "லா",
    "லி",
    "லீ",
    "லு",
    "லூ",
    "லெ",
    "லே",
    "லை",
    "லொ",
    "லோ",
    "லௌ",
    "வ",
    "வா",
    "வி",
    "வீ",
    "வு",
    "வூ",
    "வெ",
    "வே",
    "வை",
    "வொ",
    "வோ",
    "வௌ",
    "ழ",
    "ழா",
    "ழி",
    "ழீ",
    "ழு",
    "ழூ",
    "ழெ",
    "ழே",
    "ழை",
    "ழொ",
    "ழோ",
    "ழௌ",
    "ள",
    "ளா",
    "ளி",
    "ளீ",
    "ளு",
    "ளூ",
    "ளெ",
    "ளே",
    "ளை",
    "ளொ",
    "ளோ",
    "ளௌ",
    "ற",
    "றா",
    "றி",
    "றீ",
    "று",
    "றூ",
    "றெ",
    "றே",
    "றை",
    "றொ",
    "றோ",
    "றௌ",
    "ன",
    "னா",
    "னி",
    "னீ",
    "னு",
    "னூ",
    "னெ",
    "னே",
    "னை",
    "னொ",
    "னோ",
    "னௌ",
    "ஃ",
]


def get_height(text):
    ##
    # create font
    font = ImageFont.truetype(FONT_FILE, FONT_SIZE)

    # measure text
    bbox = font.getbbox(text)

    # width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]

    return height + 8


def get_max_height():
    font = ImageFont.truetype(FONT_FILE, FONT_SIZE)
    ascent, descent = font.getmetrics()

    return ascent + descent


def create_bitmap(text, varname, ht):
    ##
    # create font
    font = ImageFont.truetype(FONT_FILE, FONT_SIZE)

    # measure text
    bbox = font.getbbox(text)
    print(f"// bbox is {bbox}")

    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if ht:
        height = ht

    ascent, descent = font.getmetrics()
    baseline = ascent

    # add small margin
    # width += 6
    # height += 12

    # create image
    # img = Image.new("1", (width, height), 1)  # 1=white
    img = Image.new("L", (width, height), 255)  # black  # type: ignore

    draw = ImageDraw.Draw(img)

    # draw black text
    # draw.text((2, 2), text, font=font, fill=0)
    # draw.text((2 - bbox[0], 0 - bbox[1]), text, font=font, fill=0)
    # draw.text((0, 0), text, font=font, fill=0)
    draw.text((2, baseline), text, font=font, fill=0, anchor="ls")

    img = img.point(
        lambda x: 0 if x < 128 else 255  # type: ignore
    )  # no grey, black or white  # type: ignore

    # save preview
    if text == "கு":
        img.save(".glyph.png")

    pixels = img.load()

    # pack bitmap
    data = []

    packed_width = (width + 7) // 8

    for y in range(height):  # type: ignore
        for xb in range(packed_width):  # type: ignore
            b = 0

            for bit in range(8):
                x = xb * 8 + bit

                if x >= width:
                    continue

                # black pixel?
                if pixels[x, y] == 0:  # type: ignore
                    b |= 0x80 >> bit

            data.append(b)

    # print("Width =", width)
    # print("Height =", height)
    # print("Bytes =", len(data))

    print(
        f"// Length of data for {varname} is {len(data)} ascent={ascent} descent={descent}"
    )
    print(f"\nconst uint8_t glyph_{varname}_bitmap[] PROGMEM = {{")
    print("\t", end="")

    for i, val in enumerate(data):
        if i % 16 == 0:
            print()
            print("\t", end="")

        print(f"0x{val:02X}, ", end="")

    print("\n};")

    print(f"\nconst Glyph glyph_{varname} = {{")
    if text == '"':
        print(f'\t"\\{text}",')
    elif text == "\\":
        print(f'\t"{text}{text}",')
    else:
        print(f'\t"{text}",')
    print(f"\t{width},")
    print(f"\t{height},")
    print(f"\tglyph_{varname}_bitmap")
    print("\n};")


def main():
    print('#include "glyphs.h"')
    print("#include <Arduino.h>")

    print()

    vars = []
    max_height = 0
    for i in chars:
        h = get_height(i)
        if h > max_height:
            max_height = h

    if max_height % 2:
        max_height += 1

    max_height = get_max_height()

    for i in ascii_chars:
        iord = ord(i)
        create_bitmap(i, f"f{FONT_SIZE}_a{iord}", max_height)
        vars.append(f"f{FONT_SIZE}_a{iord}")

    idx = 0
    for i in tamil_chars:
        create_bitmap(i, f"f{FONT_SIZE}_t{idx}", max_height)
        vars.append(f"f{FONT_SIZE}_t{idx}")
        idx += 1

    print(f"const Glyph glyphs_f{FONT_SIZE}[] = {{")
    for i in vars:
        print(f"\tglyph_{i},")
    print("\n};")

    print(
        f"const size_t glyphs_f{FONT_SIZE}_count = sizeof(glyphs_f{FONT_SIZE}) / sizeof(Glyph);"
    )


main()
