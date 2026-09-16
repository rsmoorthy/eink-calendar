from PIL import Image
import sys

WIDTH = 64
HEIGHT = 64

file = sys.argv[1] if len(sys.argv) > 1 else "vinakaya.png"

name = sys.argv[2] if len(sys.argv) > 2 else "vinakaya_small"

WIDTH = int(sys.argv[3]) if len(sys.argv) > 3 else 64

HEIGHT = int(sys.argv[4]) if len(sys.argv) > 4 else 64

img = Image.open(file)

# convert to grayscale
img = img.convert("L")

# resize
# print(f"resizing image to {WIDTH} {HEIGHT}")
img = img.resize((WIDTH, HEIGHT))

# threshold to pure black/white
img = img.point(lambda x: 0 if x < 128 else 255, "1")  # type: ignore

pixels = img.load()

data = []

for y in range(HEIGHT):
    for xbyte in range(WIDTH // 8):
        b = 0

        for bit in range(8):
            x = xbyte * 8 + bit

            # white=1 black=0 usually
            if pixels[x, y]:  # type: ignore
                b |= 0x80 >> bit

        data.append(b)

print(f"const unsigned char {name}[] PROGMEM = {{")
for i, b in enumerate(data):
    if i % 16 == 0:
        print()
    print(f"0x{b:02X}, ", end="")
print("\n};")
