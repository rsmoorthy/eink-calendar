from PIL import Image, ImageDraw, ImageFont

FONT_FILE = "NotoSansTamil-Regular.ttf"
font = ImageFont.truetype(FONT_FILE, 32)

img = Image.new("L", (200, 100), 255)
draw = ImageDraw.Draw(img)

# Draw baseline
draw.line((0, 50, 200, 50), fill=128)

draw.text((2, 50), "குறள்", font=font, fill=0, anchor="ls")

img.save("baseline.png")
