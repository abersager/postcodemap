# UK postcode map data pipeline.
#
#   make            download + build everything (needs tippecanoe, uv, curl)
#   make sample     quick build of a few areas (SAMPLE_AREAS) for development
#   make clean      remove generated data (keeps downloads)
#
# Inputs (override on the command line, e.g. `make SOURCE=onspd ONSPD_ZIP=...`).
# Keep comments on their own lines: make keeps trailing spaces in values.
#
# SOURCE: codepoint | onspd | csv
SOURCE        ?= codepoint
CODEPOINT_URL ?= https://api.os.uk/downloads/v1/products/CodePointOpen/downloads?area=GB&format=CSV&redirect
CODEPOINT_ZIP ?= data/raw/codepo_gb.zip
# ONSPD_ZIP: download manually from https://geoportal.statistics.gov.uk/ (search "ONS Postcode Directory")
ONSPD_ZIP     ?= data/raw/onspd.zip
# CSV_FILE: any postcode,lat,lon CSV (or zip of one) when SOURCE=csv
CSV_FILE      ?=
# INCLUDE_NI: 1 keeps Northern Ireland rows from ONSPD (separate licence, see docs/CAVEATS.md)
INCLUDE_NI    ?= 0
COASTLINE     ?= data/raw/coastline.geojson
# COASTLINE_URL: leave empty to auto-discover the newest ONS "Countries ... UK BGC" layer
COASTLINE_URL ?=
SAMPLE_AREAS  ?= SW,W,WC,EC
# PYTHON: interpreter for the pipeline scripts; deps come from pyproject.toml / uv.lock
PYTHON        ?= uv run python

BUILD   ?= data/build
WEBPUB  := web/public
UNITS    = $(BUILD)/units.csv
POLYS    = $(BUILD)/polygons
TILES   := $(WEBPUB)/tiles
INDEX   := $(WEBPUB)/data

ifeq ($(SOURCE),codepoint)
  INPUT := $(CODEPOINT_ZIP)
else ifeq ($(SOURCE),onspd)
  INPUT := $(ONSPD_ZIP)
else
  INPUT := $(CSV_FILE)
endif
NI_FLAG := $(if $(filter 1,$(INCLUDE_NI)),--include-ni,)
AREAS_FLAG ?=

.PHONY: all sample download coastline points polygons tiles index clean distclean check-tools

all: check-tools download coastline points polygons tiles index
	@echo "Done. Run: npm run dev"

# The sample build uses its own build dir so it never masks a full build.
sample:
	$(MAKE) all BUILD=data/build-sample AREAS_FLAG="--areas $(SAMPLE_AREAS)"
	@echo "Sample build ($(SAMPLE_AREAS)) done. Run: npm run dev"

check-tools:
	@command -v tippecanoe >/dev/null || { echo "tippecanoe not found: see pipeline/README.md"; exit 1; }
	@command -v tile-join  >/dev/null || { echo "tile-join not found (ships with tippecanoe)"; exit 1; }
	@command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	@$(PYTHON) -c "import shapely, scipy, pyproj, numpy" 2>/dev/null || { echo "python deps could not be installed (uv sync failed?)"; exit 1; }

download: $(INPUT)

$(CODEPOINT_ZIP):
	mkdir -p data/raw
	curl -L --fail --retry 3 -o $@ "$(CODEPOINT_URL)"

$(ONSPD_ZIP):
	@echo "Download the ONS Postcode Directory zip manually to $@ (see pipeline/README.md)"; exit 1

# Coastline is optional: if the download fails the polygon step falls back to a
# point-derived mask. Delete the empty marker file to retry.
coastline:
	@mkdir -p data/raw
	@test -s $(COASTLINE) || $(PYTHON) pipeline/fetch_coastline.py --out $(COASTLINE) $(if $(COASTLINE_URL),--url "$(COASTLINE_URL)",) || echo "WARNING: coastline unavailable, will use point-derived mask"

points: $(UNITS)
$(UNITS): $(INPUT) pipeline/build_points.py pipeline/postcode.py
	mkdir -p $(BUILD)
	$(PYTHON) pipeline/build_points.py "$(INPUT)" --format $(SOURCE) --out $@ $(NI_FLAG) $(AREAS_FLAG)

polygons: $(POLYS)/sectors.geojsonl
$(POLYS)/sectors.geojsonl: $(UNITS) pipeline/build_polygons.py
	$(PYTHON) pipeline/build_polygons.py $(UNITS) --out $(POLYS) --report $(BUILD)/report.json $$( [ -s "$(COASTLINE)" ] && echo --coastline "$(COASTLINE)" )

# Tiles and index are always (re)written into web/public so the app serves the
# most recent build, sample or full.
tiles: $(POLYS)/sectors.geojsonl pipeline/build_tiles.sh
	TMP_DIR=$(BUILD)/tiles pipeline/build_tiles.sh $(POLYS) $(UNITS) $(TILES)

index: $(POLYS)/sectors.geojsonl pipeline/build_index.py
	rm -rf $(INDEX)
	$(PYTHON) pipeline/build_index.py $(UNITS) --polygons $(POLYS) --out $(INDEX)

clean:
	rm -rf $(BUILD) $(TILES) $(INDEX)

distclean: clean
	rm -rf data/raw
