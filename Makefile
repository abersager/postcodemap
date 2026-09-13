# Postcode map data pipeline, one country at a time.
#
#   make                      build Great Britain (COUNTRY=gb)
#   make COUNTRY=at           build Austria
#   make sample COUNTRY=gb SAMPLE_AREAS=SW,EH   quick build of a few top-level codes
#   make clean COUNTRY=at     remove that country's generated data (keeps downloads)
#
# Countries are modules in pipeline/countries/. Outputs go to
# web/public/countries/<cc>/ (tiles, search index, meta.json), raw downloads
# and intermediate files to data/<cc>/. Nothing generated is committed.
#
# GB-only variables (read by pipeline/countries/gb.py):
#   SOURCE=codepoint|onspd|csv   ONSPD_ZIP=...   CSV_FILE=...   INCLUDE_NI=1   COASTLINE_URL=...
COUNTRY      ?= gb
SAMPLE_AREAS ?= SW,W,WC,EC
PYTHON       ?= uv run python
export SOURCE ONSPD_ZIP CSV_FILE INCLUDE_NI COASTLINE_URL

RAW    = data/$(COUNTRY)/raw
BUILD ?= data/$(COUNTRY)/build
OUT    = web/public/countries/$(COUNTRY)
UNITS  = $(BUILD)/units.csv
POLYS  = $(BUILD)/polygons
AREAS_FLAG ?=

.PHONY: all sample download points polygons tiles index clean distclean check-tools

all: check-tools download points polygons tiles index
	@echo "Done ($(COUNTRY)). Run: npm run dev"

# Sample builds use their own build dir so they never mask a full build.
sample:
	$(MAKE) all COUNTRY=$(COUNTRY) BUILD=data/$(COUNTRY)/build-sample AREAS_FLAG="--areas $(SAMPLE_AREAS)"

check-tools:
	@command -v tippecanoe >/dev/null || { echo "tippecanoe not found: see pipeline/README.md"; exit 1; }
	@command -v tile-join  >/dev/null || { echo "tile-join not found (ships with tippecanoe)"; exit 1; }
	@command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	@$(PYTHON) -c "import shapely, scipy, pyproj, numpy, shapefile" 2>/dev/null || { echo "python deps could not be installed (uv sync failed?)"; exit 1; }

download:
	$(PYTHON) pipeline/download.py $(COUNTRY) $(RAW)

points: $(UNITS)
$(UNITS): pipeline/build_points.py pipeline/countries/$(COUNTRY).py
	mkdir -p $(BUILD)
	$(PYTHON) pipeline/build_points.py $(COUNTRY) $(RAW) --out $@ $(AREAS_FLAG)

polygons: $(POLYS)/.done
$(POLYS)/.done: $(UNITS) pipeline/build_polygons.py
	$(PYTHON) pipeline/build_polygons.py $(COUNTRY) $(RAW) $(UNITS) --out $(POLYS) --report $(BUILD)/report.json --mask-cache data/$(COUNTRY)/mask-cache.pkl
	touch $@

# Tiles and index are always (re)written so the app serves the latest build.
tiles: $(POLYS)/.done pipeline/build_tiles.py
	$(PYTHON) pipeline/build_tiles.py $(COUNTRY) $(POLYS) $(UNITS) --out $(OUT) --tmp $(BUILD)/tiles

index: $(POLYS)/.done pipeline/build_index.py
	rm -rf $(OUT)/index.json $(OUT)/units $(OUT)/units.bin
	$(PYTHON) pipeline/build_index.py $(COUNTRY) $(POLYS) $(UNITS) --out $(OUT)

clean:
	rm -rf $(BUILD) data/$(COUNTRY)/build-sample $(OUT)

distclean: clean
	rm -rf data/$(COUNTRY)
