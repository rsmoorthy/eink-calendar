# CR2 - Add "Next Ekadashi" field


A new requirement. To plan ahead, the user needs to be know when is the next ekadashi. Let there be a field created in each 
day called nextEkadashi, which will also be available on the Web UI (under Contents). Let the same be reflected in the image,
configured via line3.next_ekadashi (similar to tithi or masa, having its own x,y,font, font_size). Let the x,y be -1, -1 
in the config.yaml, I will set a right place for this.

The contents of this field will be "N.Eka: <Gregorian Mon name in 3 letters like Jan|Feb|Mar> <date>". The default will be "N.Eka: -" (dash)

To update this field, you could consider a 2-pass approach. First, we will update all the fields like Tithi, festival etc 
in the 1st pass. In the second pass, will update nextEkadashi field, only if we the next ekadashi (ie. Tithi in DB having Ekadashi)
is in the DB. So, if we are asked to update a 90 day period, it is quite possible that the last ~14 days may not have nextEkadashi 
updated. Which is just fine.
