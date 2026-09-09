# Data caveats

## Official vs derived

| Layer     | Status        | Detail                                                                                   |
|-----------|---------------|------------------------------------------------------------------------------------------|
| Units     | **Official**  | Centroids from OS Code-Point Open (Royal Mail PAF + OS positioning). A point marks the mean position of the delivery points in a postcode, snapped to the nearest address; it is not a boundary. Royal Mail publishes no unit boundaries. |
| Sectors   | **Derived**   | Union of the Voronoi cells of the sector's unit centroids, clipped to the coastline.      |
| Districts | **Derived**   | Union of derived sectors.                                                                |
| Areas     | **Derived**   | Union of derived districts.                                                              |
| Coastline | Official      | ONS country boundaries (BGC, generalised 20 m), OGL. Used only as a clip mask.           |

What "derived" means in practice:

- A boundary runs halfway between the nearest postcodes on either side. In
  dense towns that is within tens of metres of the real delivery boundary;
  in rural areas a boundary may wander kilometres across open land because
  nothing constrains it there.
- Postcodes have no legal boundaries at all, so there is no ground truth for
  areas, districts or sectors. Royal Mail's own polygon products (sold by OS
  as Code-Point with Polygons) are themselves constructed from delivery
  points.
- Non-geographic and large-user postcodes (PO boxes, big organisations that
  have their own sector, e.g. W1A) either have no coordinates and are
  dropped, or share a location with ordinary postcodes and get no polygon.
  `data/build/report.json` lists them after each build.
- Water narrower than 400 m and lakes under 4 km² are treated as land when
  clipping, so tidal rivers do not cut polygons into parts. Wide estuaries
  (Thames, Humber, Severn, Solent, the Scottish firths) do split them, which
  matches how postcodes work on opposite banks.
- Where the pipeline could not download the ONS coastline it clips to a
  dilated 1 km grid of the points instead. That is visible as a stepped
  coast and is recorded in `report.json` as `"mask": "grid"`.
- Isle of Man, Guernsey and Jersey (IM, GY, JE) are not in Code-Point Open
  or ONSPD and do not appear.

## Licences

- **OS Code-Point Open**: Open Government Licence v3. You must show
  *Contains OS data © Crown copyright and database right [year]* and
  *Contains Royal Mail data © Royal Mail copyright and database right [year]*.
  Derived works (these polygons) may be published under OGL with the same
  attribution.
- **ONS Postcode Directory (ONSPD)**: OGL v3 for England, Scotland and
  Wales. **Northern Ireland postcodes (BT) are excluded from OGL**: they are
  released under a Northern Ireland End User Licence that allows internal
  business use only; publishing a map that includes them needs a licence
  from Land & Property Services. This pipeline drops BT rows from ONSPD
  unless you set `INCLUDE_NI=1`, and that flag is for internal use.
- **ONS boundaries** (coastline mask): OGL v3, *Source: Office for National
  Statistics licensed under the Open Government Licence v.3.0* and
  *Contains OS data © Crown copyright and database right [year]*.
- **Basemap**: OpenFreeMap tiles are free to use; the data is © OpenStreetMap
  contributors (ODbL) and the style © OpenMapTiles. MapLibre adds their
  attribution from the style. If you switch to OS Open Zoomstack via the OS
  Data Hub, an API key and the OS attribution line are required.
- **This repository's code**: see LICENSE (MIT).

## Currency and refresh

Royal Mail changes postcodes continuously; OS republishes Code-Point Open
quarterly (February, May, August, November) and ONS republishes ONSPD on the
same cadence. To refresh:

```bash
make distclean && make      # re-download and rebuild everything
npm run build               # then redeploy dist/
```

Update the copyright years in `web/config.js` and `pipeline/build_tiles.sh`
each January. The ONS coastline is discovered automatically (newest
"Countries ... Boundaries UK BGC" service); pin a specific edition with
`COASTLINE_URL=` if you need reproducibility across years.

Terminated postcodes are not shown (Code-Point Open only ships live ones;
the ONSPD reader drops rows with a termination date).
