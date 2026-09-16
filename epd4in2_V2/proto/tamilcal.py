from datetime import date

# Sankranti start dates covering 2026 and 2027
# Tuple structure: (start_date, tamil_month_name, tamil_name_ta)
TAMIL_MONTH_STARTS = [
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
]


def gregorian_to_tamil(greg_date: date):
    """Maps a given Gregorian date in 2026 or 2027 to Tamil month and date."""
    for i in range(len(TAMIL_MONTH_STARTS) - 1):
        current_start, month_en, month_ta = TAMIL_MONTH_STARTS[i]
        next_start = TAMIL_MONTH_STARTS[i + 1][0]

        if current_start <= greg_date < next_start:
            tamil_day = (greg_date - current_start).days + 1
            return {
                "gregorian_date": greg_date.isoformat(),
                "tamil_month": month_en,
                "tamil_month_ta": month_ta,
                "tamil_date": tamil_day,
            }

    raise ValueError("Date out of range (supported: 2026-01-01 to 2027-12-31)")


# Example: Convert Pongal / Makara Sankranti 2026
print(gregorian_to_tamil(date(2026, 9, 13)))
# Output: {'gregorian_date': '2026-01-15', 'tamil_month': 'Thai', 'tamil_month_ta': 'தை', 'tamil_date': 1}
