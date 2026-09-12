# Beyond Great Britain: which countries have open postcode data?

Investigated 2026-09-12 by web search against the primary sources named
below. "Verified" means the publisher's own page or catalogue entry was found
stating the licence; "reported" means a secondary source says so and it
should be confirmed before building on it.

## Verdict

A true *world* postcode map at this app's four levels is not possible from
open data: several large postal operators sell their postcode data (Canada,
Sweden, Ireland, Italy, Brazil, New Zealand) and most of the world outside
Europe, North America and East Asia has no open unit-level data at all. What
*is* possible is a multi-country map covering roughly 20 countries with
official open data, most of them at full resolution, plus a coarser
"approximate" layer from GeoNames for around 80 more. Recommended: build it
as a set of per-country datasets sharing one app, not one global dataset,
because the licences differ and must not be mixed.

## Tier 1: official open data, full resolution, permissive licence

| Country | System | Levels for the app | Open source (form) | Licence |
|---|---|---|---|---|
| Netherlands | 1234 AB (PC6) | PC2, PC4, PC5, PC6 | CBS/Kadaster PC6 polygons on PDOK; BAG address points | Verified: CC0 / CC BY 4.0 |
| Denmark | 4 digits | 1, 2, 4 digits | DAWA/DAGI postnumre polygons; address points | Verified: CC BY 4.0 |
| Norway | 4 digits | 1, 2, 4 digits | Kartverket "Postnummerområder" polygons (boundaries from Posten) | Verified: CC BY 4.0 |
| Finland | 5 digits | 2, 3, 5 digits | Statistics Finland Paavo postal-code area polygons | Verified: Statistics Finland open data terms (CC BY 4.0) |
| Switzerland + Liechtenstein | 4 digits | 1, 2, 4 digits (+PLZ6) | swisstopo "Amtliches Ortschaftenverzeichnis mit PLZ und Perimeter" polygons | Verified: Swiss OGD, free |
| Austria | 4 digits | 1, 2, 4 digits | **Built.** BEV Adressregister (2.5 M geocoded addresses with PLZ, twice yearly); RTR postcode list for names; Statistik Austria municipalities as mask. No official PLZ polygons exist (the data.gv.at "Postleitzahlen" entry is RTR's CSV list) | Verified: BEV licence (attribution required), RTR CC BY 4.0, Statistik Austria CC BY 4.0 |
| Spain | 5 digits | 2 (province), 3, 5 digits | IGN CartoCiudad "Códigos postales" polygons (WFS/download) | Verified: CC BY 4.0 |
| Belgium | 4 digits | 1, 2, 4 digits | bpost postcode polygons via data.gov.be / regional portals | Reported open (bpost); confirm terms per file |
| France | 5 digits | 2 (département), 5 digits | BAN address points with code postal (25 M addresses); La Poste postcode base | Verified: Licence Ouverte 2.0 (BAN also as ODbL via OSM-FR; use the LO build) |
| Czechia | 5 digits (3+2) | 1, 3, 5 digits | RÚIAN address points with PSČ (ČÚZK) | Verified: CC BY 4.0 |
| Estonia | 5 digits | 2, 5 digits | Maa-amet ADS address extracts incl. postal codes | Verified: open data, no licence agreement |
| Australia | 4 digits | state digit, 2, 4 digits | G-NAF address points with postcode; ABS Postal Areas polygons | Verified: open licence (data.gov.au), ABS CC BY 4.0 |
| United States | 5-digit ZIP | 1, 3 (sectional centre), 5 digits | Census TIGER ZCTA5 polygons | Verified: public domain. Note ZCTAs approximate ZIPs; ~10k ZIPs have no ZCTA; ZIP+4 is USPS-proprietary |
| Mexico | 5 digits | 2 (state), 5 digits | SEPOMEX postcode polygons by state on datos.gob.mx | Reported open (Mexican government open data terms) |
| Japan | 7 digits (3+4) | 2, 3, 7 digits | Japan Post KEN_ALL list (CC0-equivalent); Geolonia japanese-addresses for coordinates | Verified free; Geolonia CC BY 4.0 (reported) |
| South Korea | 5 digits | 2, 5 digits | juso.go.kr address/postcode data with coordinates | Reported open; confirm licence on the portal |
| Singapore | 6 digits | 2 (sector), 6 digits | OneMap building/postal-code data via API | Verified: SLA Open Data Licence, commercial use allowed; no bulk file, must be harvested via API |
| Luxembourg | 4 digits | 1, 2, 4 digits | National address register on data.public.lu | Reported CC0; not confirmed in this pass |

For point-only sources (FR, CZ, EE, AU G-NAF, JP, KR, SG) the existing
Voronoi pipeline applies unchanged: derive polygons from the points and mark
them derived, exactly as for GB.

## Tier 2: open but partial, approximate, or awkward

| Country | What exists | Problem |
|---|---|---|
| Germany | No official open PLZ data (Deutsche Post sells it; BKG redistributes only to public bodies). Complete PLZ polygons exist in OpenStreetMap, redistributed by suche-postleitzahl.org and yetzt/postleitzahlen. | ODbL share-alike. Usable as a *separate* ODbL-licensed country dataset with OSM attribution, never merged with OGL/CC BY data. |
| Poland | Poczta Polska PNA list is open (dane.gov.pl) but has no coordinates; GUGiK PRG address points are open but the PNA join is by locality/street. | Needs a join pipeline; expect gaps. |
| Canada | Statistics Canada FSA (3-character) boundaries are open. | Full 6-character codes are Canada Post copyright; StatCan's PCCF is excluded from the open licence. Two levels only. |
| Portugal | CTT provides the full list (~300k entries) after registration; geocoding via OpenAddresses/OSM. | Terms of use unclear, no explicit open licence. |
| India | data.gov.in "All India Pincode Directory" with coordinates. | Coordinates present for only a small subset of post offices; GODL variant reported as non-commercial. |
| Ireland | Eircode routing keys (first 3 characters) can be approximated; full Eircodes are licensed (ECAD/ECAF, paid). | Unit level not open; OSM explicitly barred. |
| Brazil | CEP is Correios' copyrighted DNE product (Law 6538/1978). Community mirrors (OpenCEP, ViaCEP) exist. | Legally derived from a proprietary base; avoid for a published map. |
| Italy | CAP polygons are a Poste Italiane commercial product ("CAP Zone"). ISTAT released a snapshot in 2009. | Not open; the 2009 snapshot is stale. |
| Sweden | PostNord owns the system, sells via Postnummerservice/Geposit (~EUR 2000/yr) and has issued takedowns. | Not open. Lantmäteriet's CC0 geodata excludes postcodes. |
| New Zealand | NZ Post Postcode Network File is commercial; LINZ addresses carry no postcodes; a community reconstruction (open_nz_postcodes) is non-commercial only. | Not open. |

## Tier 3: global fill

- **GeoNames postal codes** (`allCountries.zip`): ~100 countries, CC BY 4.0,
  one row per postcode with a place name and a centroid, accuracy graded 1–6
  and often computed from place names rather than measured. For GB, NL and
  CA only the outward part is included. Good enough for an "approximate"
  world layer at area/district level, not for units.
- **OpenAddresses**: address points with postcodes from hundreds of
  government sources; the licence is whatever the source has, listed per
  source, mixing attribution-only and share-alike. Use it as a discovery
  index for national sources rather than as a dataset.
- **OpenStreetMap** `boundary=postal_code` relations: complete in Belgium and
  Germany, patchy elsewhere; ODbL.
- **Who's On First** postal codes: mixed provenance, per-country licences.

## What the app and pipeline would need

1. **Country modules.** One reader per source (points or polygons) and one
   small hierarchy definition per country: how to split a code into the
   app's levels (e.g. NL `1234 AB` → `12`, `1234`, `1234 A`, `1234 AB`; US
   ZIP → 1, 3, 5 digits). The existing GB parsing is one such module.
2. **Per-country datasets.** Separate `units.csv`, polygons, tiles and
   index per country, each with its own attribution string, so a CC BY,
   CC0, OGL or ODbL dataset never becomes one derived database. The app
   would load the tileset for the country under the map centre (or a small
   set) instead of two fixed archives.
3. **Clipping.** Voronoi derivation needs a land mask per country. Natural
   Earth is too coarse at z10+; use each country's own open boundary (most
   Tier 1 countries publish one) or OSM land polygons (ODbL, but a mask
   does not enter the output geometry's licence in the same way as source
   points; take advice if that matters).
4. **Search.** Postcode syntax differs per country, so the fragment parser
   becomes per-country too; the index shards by country then district.
5. **Density rule.** Already generic; needs each country's polygons to carry
   `units` and `km2`.
6. **Scale.** Netherlands alone has 460k PC6 codes, France 25 M addresses
   (but only ~6k codes), Japan ~120k 7-digit codes, the US ~33k ZCTAs.
   Total is a few times GB, fine for the current tooling.

## Suggested order

1. Netherlands, Denmark, Norway, Finland, Switzerland, Austria, Spain:
   official polygons under permissive licences. No derivation needed, just
   readers, and they exercise the multi-country plumbing.
2. France, Czechia, Estonia, Australia: official points, derived polygons
   with the pipeline as it stands.
3. United States (ZCTA) and Mexico (SEPOMEX polygons): large but simple.
4. Japan, South Korea, Singapore: workable, more parsing effort.
5. Germany as a clearly labelled ODbL dataset from OpenStreetMap.
6. Everything else via GeoNames, labelled approximate, area/district only.

Countries in Tier 2's lower half (Canada beyond FSA, Sweden, Ireland, Italy,
Brazil, New Zealand) should stay out until their operators open the data.
