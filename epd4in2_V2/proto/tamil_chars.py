# 12 Uyir letters
uyir = ["அ", "ஆ", "இ", "ஈ", "உ", "ஊ", "எ", "ஏ", "ஐ", "ஒ", "ஓ", "ஔ"]

# Aytham
aytham = ["ஃ"]

# 18 Mei letters (base consonants)
base = [
    "க",
    "ங",
    "ச",
    "ஞ",
    "ட",
    "ண",
    "த",
    "ந",
    "ப",
    "ம",
    "ய",
    "ர",
    "ல",
    "வ",
    "ழ",
    "ள",
    "ற",
    "ன",
]

# Mei forms (with pulli)
mei = [
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
]

# Vowel signs corresponding to:
# ஆ, இ, ஈ, உ, ஊ, எ, ஏ, ஐ, ஒ, ஓ, ஔ
signs = [
    "",  # அ
    "ா",  # ஆ
    "ி",  # இ
    "ீ",  # ஈ
    "ு",  # உ
    "ூ",  # ஊ
    "ெ",  # எ
    "ே",  # ஏ
    "ை",  # ஐ
    "ொ",  # ஒ
    "ோ",  # ஓ
    "ௌ",  # ஔ
]

# Build 216 uyirmei letters
uyirmei = []

for consonant in base:
    for sign in signs:
        uyirmei.append(consonant + sign)

# Traditional 247 letters
tamil247 = uyir + mei + uyirmei + aytham

print("Count =", len(tamil247))
assert len(tamil247) == 247

print(tamil247)
# for x in tamil247:
#    print(repr(x))
