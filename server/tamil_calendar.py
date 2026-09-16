from datetime import date

# Sankranti start dates covering 2024 to 2028
# Tuple structure: (start_date, tamil_month_name, tamil_name_ta)
TAMIL_MONTH_STARTS = [
    (date(2024, 1, 15), "Thai", "தை"),
    (date(2024, 2, 14), "Maasi", "மாசி"),
    (date(2024, 3, 14), "Panguni", "பங்குனி"),
    (date(2024, 4, 14), "Chithirai", "சித்திரை"),
    (date(2024, 5, 14), "Vaikasi", "வைகாசி"),
    (date(2024, 6, 15), "Aani", "ஆனி"),
    (date(2024, 7, 16), "Aadi", "ஆடி"),
    (date(2024, 8, 17), "Avani", "ஆவணி"),
    (date(2024, 9, 17), "Purattasi", "புரட்டாசி"),
    (date(2024, 10, 17), "Aippasi", "ஐப்பசி"),
    (date(2024, 11, 16), "Karthigai", "கார்த்திகை"),
    (date(2024, 12, 16), "Margazhi", "மார்கழி"),

    (date(2025, 1, 14), "Thai", "தை"),
    (date(2025, 2, 13), "Maasi", "மாசி"),
    (date(2025, 3, 15), "Panguni", "பங்குனி"),
    (date(2025, 4, 14), "Chithirai", "சித்திரை"),
    (date(2025, 5, 15), "Vaikasi", "வைகாசி"),
    (date(2025, 6, 15), "Aani", "ஆனி"),
    (date(2025, 7, 16), "Aadi", "ஆடி"),
    (date(2025, 8, 17), "Avani", "ஆவணி"),
    (date(2025, 9, 17), "Purattasi", "புரட்டாசி"),
    (date(2025, 10, 17), "Aippasi", "ஐப்பசி"),
    (date(2025, 11, 16), "Karthigai", "கார்த்திகை"),
    (date(2025, 12, 16), "Margazhi", "மார்கழி"),

    (date(2026, 1, 15), "Thai", "தை"),
    (date(2026, 2, 13), "Maasi", "மாசி"),
    (date(2026, 3, 15), "Panguni", "பங்குனி"),
    (date(2026, 4, 14), "Chithirai", "சித்திரை"),
    (date(2026, 5, 15), "Vaikasi", "வைகாசி"),
    (date(2026, 6, 15), "Aani", "ஆனி"),
    (date(2026, 7, 17), "Aadi", "ஆடி"),
    (date(2026, 8, 17), "Avani", "ஆவணி"),
    (date(2026, 9, 17), "Purattasi", "புரட்டாசி"),
    (date(2026, 10, 18), "Aippasi", "ஐப்பசி"),
    (date(2026, 11, 17), "Karthigai", "கார்த்திகை"),
    (date(2026, 12, 16), "Margazhi", "மார்கழி"),

    (date(2027, 1, 15), "Thai", "தை"),
    (date(2027, 2, 13), "Maasi", "மாசி"),
    (date(2027, 3, 15), "Panguni", "பங்குனி"),
    (date(2027, 4, 14), "Chithirai", "சித்திரை"),
    (date(2027, 5, 15), "Vaikasi", "வைகாசி"),
    (date(2027, 6, 15), "Aani", "ஆனி"),
    (date(2027, 7, 17), "Aadi", "ஆடி"),
    (date(2027, 8, 17), "Avani", "ஆவணி"),
    (date(2027, 9, 17), "Purattasi", "புரட்டாசி"),
    (date(2027, 10, 18), "Aippasi", "ஐப்பசி"),
    (date(2027, 11, 17), "Karthigai", "கார்த்திகை"),
    (date(2027, 12, 16), "Margazhi", "மார்கழி"),

    (date(2028, 1, 15), "Thai", "தை"),
    (date(2028, 2, 14), "Maasi", "மாசி"),
    (date(2028, 3, 14), "Panguni", "பங்குனி"),
    (date(2028, 4, 13), "Chithirai", "சித்திரை"),
    (date(2028, 5, 14), "Vaikasi", "வைகாசி"),
]

TAMIL_MONTHS_SEQUENCE = [
    ("Chithirai", "சித்திரை"),
    ("Vaikasi", "வைகாசி"),
    ("Aani", "ஆனி"),
    ("Aadi", "ஆடி"),
    ("Avani", "ஆவணி"),
    ("Purattasi", "புரட்டாசி"),
    ("Aippasi", "ஐப்பசி"),
    ("Karthigai", "கார்த்திகை"),
    ("Margazhi", "மார்கழி"),
    ("Thai", "தை"),
    ("Maasi", "மாசி"),
    ("Panguni", "பங்குனி"),
]


def get_tamil_date(target_date: date) -> dict:
    """
    Computes Tamil month (English and Tamil) and Tamil day number for a given Gregorian date.
    """
    for i in range(len(TAMIL_MONTH_STARTS) - 1):
        current_start, month_en, month_ta = TAMIL_MONTH_STARTS[i]
        next_start = TAMIL_MONTH_STARTS[i + 1][0]

        if current_start <= target_date < next_start:
            tamil_day = (target_date - current_start).days + 1
            return {
                "tamil_month": month_en,
                "tamil_month_ta": month_ta,
                "tamil_date": tamil_day,
            }

    # Fallback estimate if date is outside hardcoded range
    approx_starts = [14, 13, 14, 14, 15, 15, 17, 17, 17, 18, 17, 16]
    m = target_date.month
    d = target_date.day
    if d >= approx_starts[m - 1]:
        idx = (m + 8) % 12
        day_num = d - approx_starts[m - 1] + 1
    else:
        prev_m = 12 if m == 1 else m - 1
        idx = (prev_m + 8) % 12
        day_num = 30 - approx_starts[prev_m - 1] + d

    month_en, month_ta = TAMIL_MONTHS_SEQUENCE[idx]
    return {
        "tamil_month": month_en,
        "tamil_month_ta": month_ta,
        "tamil_date": max(1, day_num),
    }
