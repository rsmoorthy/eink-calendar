# CR1 - Change request - Panchanga decoding

I am now made aware of slight nuances in how to read panchanga from vyasarajamatha.org/panchanga.php

The following additional rules apply:

1. When you read that HTML, you get few LI, including Tithi, Shraddha Tithi, Festivals/Events. In the last iteration, the request was to only
   look at `Shraddha Tithi` and use it for the field `Tithi` in the DB. But that will be different from now on.
2. If the Shraddha Tithi says "SHRADDHABHAVA", then consider the LI element that has `Tithi` and take its value for DB field Tithi.
3. If the Shraddha Tithi has a "/" character (like "EKADASHI/DVADASHI"), then consider the LI element that has `Tithi` and take its value for DB field Tithi.
4. Else, consider the LI element `Shraddha Tithi` and use its value for `Tithi` in DB.
5. In addition, Take the Festivals/Events and store it as an additional field `Festival` in the DB.
6. If the DB field `Custom text` is `None` or empty, and DB `Festival` is present, use this `Festival` field to fill up the custom text in the image.
7. If the DB field Custom text has some other text, then use that field to fill up the custom text in the image.


```
