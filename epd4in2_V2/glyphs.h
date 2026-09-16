
/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __GLYPHS_H
#define __GLYPHS_H

/* Includes ------------------------------------------------------------------*/
#include <stdint.h>
#include <cstddef>

struct Glyph {
  const char *utf8;
  uint8_t width;
  uint8_t height;
  const uint8_t *bitmap;
};

// 16 font
extern const Glyph glyphs_f16[];
extern const size_t glyphs_f16_count;

// 20 font
extern const Glyph glyphs_f20[];
extern const size_t glyphs_f20_count;

// 24 font
extern const Glyph glyphs_f24[];
extern const size_t glyphs_f24_count;

// 32 font
extern const Glyph glyphs_f32[];
extern const size_t glyphs_f32_count;

// 64 font
extern const Glyph glyphs_f64[];
extern const size_t glyphs_f64_count;

#endif /* __FONTS_H */
