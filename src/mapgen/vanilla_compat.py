"""
Vanilla HOI4 compatibility layer for map generation.

Ported from RandomParadox:
  - BMP colour table extraction from vanilla game files
    (Hoi4ImageExporter.cpp:16-44)
  - BMP 8-bit save with correct palette + header
    (FormatConverter.cpp:382,455,493,551 + Bmp::save8bit)
  - Colour mapping tables: terrain, rivers, trees, cities
    (FormatConverter.cpp:6-333)
  - Mod descriptor template with conservative replace_paths
    (resources/hoi4/descriptor.mod)
  - State, strategic region, country, bookmark templates
    (resources/hoi4/history/state.txt, map/strategic_region.txt, ...)

All templateVariable placeholders from RandomParadox become {variable} Python
format-string keys.
"""

from __future__ import annotations

import struct
from pathlib import Path

import PIL.Image

# ---------------------------------------------------------------------------
# BMP colour table extraction (== Hoi4ImageExporter constructor)
# ---------------------------------------------------------------------------


def extract_vanilla_palette(game_path: Path, bmp_name: str) -> list[int]:
    """Read a vanilla HOI4 .bmp and extract its 256-entry raw palette.

    RandomParadox reads terrain.bmp, rivers.bmp, trees.bmp, heightmap.bmp
    from the base game install and stores `colourtable` for each.  PIL's
    ``Image.getpalette()`` returns the same raw 768-byte list.

    HOI4 pushes 4 extra zero-bytes after the palette (colourTable.push_back(0)×4)
    for a total of 772 bytes.
    """
    img = PIL.Image.open(game_path / "map" / bmp_name)
    palette = img.getpalette()
    if palette is None:
        # PIL returns None for non-indexed images; treat as empty
        raise ValueError(f"Not an indexed BMP: {bmp_name} (path={game_path})")
    raw = list(palette)  # 768 bytes = 256 × RGB
    raw.extend([0, 0, 0, 0])  # match push_back(0)×4
    return raw


def extract_all_vanilla_palettes(game_path: Path) -> dict[str, list[int]]:
    """Extract all palettes RandomParadox reads at startup.

    Returns a dict keyed by the same identifiers RandomParadox uses internally:
    ``terrainHoi4``, ``citiesHoi4``, ``riversHoi4``, ``treesHoi4``, ``heightmapHoi4``.
    """
    # RandomParadox reads cities palette from terrain.bmp (same file, different usage)
    terrain = extract_vanilla_palette(game_path, "terrain.bmp")
    return {
        "terrainHoi4": terrain,
        "citiesHoi4": terrain,  # Hoi4ImageExporter.cpp:27-28 ; cities = terrain.colourtable
        "riversHoi4": extract_vanilla_palette(game_path, "rivers.bmp"),
        "treesHoi4": extract_vanilla_palette(game_path, "trees.bmp"),
        "heightmapHoi4": extract_vanilla_palette(game_path, "heightmap.bmp"),
    }


# ---------------------------------------------------------------------------
# BMP saving with vanilla palette  (== Bmp::save8bit + header fix)
# ---------------------------------------------------------------------------


def _fix_bmp_header(path: Path) -> None:
    """Patch clrUsed and clrImp to 0 in a BMP header.

    PIL writes clrUsed=256 for 8-bit images; HOI4 expects 0 (meaning
    "use all palette entries").  Mismatch causes MAP_ERROR log spam.
    """
    with open(path, "r+b") as f:
        f.seek(46)
        f.write(struct.pack("<I", 0))
        f.seek(50)
        f.write(struct.pack("<I", 0))


def save_indexed_bmp(
    img: PIL.Image.Image,
    path: Path,
    palette: list[int],
) -> None:
    """Save an 8-bit indexed BMP with a vanilla palette + patched header.

    Call this instead of plain ``img.save(path, format="BMP")`` for every
    indexed map BMP (terrain, rivers, trees, heightmap, cities).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    img.putpalette(palette)
    img.save(path, format="BMP")
    _fix_bmp_header(path)


# ---------------------------------------------------------------------------
# Colour mapping tables  (== FormatConverter.cpp colourMaps + indexMaps)
# ---------------------------------------------------------------------------
# Each dict maps an internal terrain/climate identifier to the palette index
# that the vanilla HOI4 colour table reserves for that pixel type.

# terrain.bmp: terrain-type string → palette index
COLOUR_MAP_TERRAIN: dict[str, int] = {
    "grassland": 0,
    "grasslandHills": 17,
    "grasslandMountains": 20,
    "desert": 3,
    "desertHills": 8,
    "desertMountains": 10,
    "forest": 4,
    "forestHills": 1,
    "forestMountains": 4,
    "savanna": 0,
    "drysavanna": 12,
    "jungle": 21,
    "tundra": 19,
    "ice": 2,
    "marsh": 9,
    "urban": 13,
    "farm": 5,
    "sea": 15,
    "lake": 15,
    "rockyHills": 2,
    "snowyHills": 16,
    "rockyMountains": 6,
    "snowyMountains": 16,
    "rockyPeaks": 11,
    "snowyPeaks": 16,
}

# (climate_class_id, elevation_mod) → palette index
# elevation_mod: 0=flat, 100=hills, 200=mountains, 300=peaks
# climate_class_id values as ints (ClimateClassId enum ordinals)
INDEX_MAP_TERRAIN: dict[tuple[int, int], int] = {
    # TROPICSRAINFOREST
    (0, 0): 21,
    (0, 100): 22,
    (0, 200): 27,
    (0, 300): 27,
    # TROPICSMONSOON
    (1, 0): 22,
    (1, 100): 22,
    (1, 200): 27,
    (1, 300): 27,
    # TROPICSSAVANNA
    (2, 0): 5,
    (2, 100): 18,
    (2, 200): 18,
    (2, 300): 27,
    # DESERT
    (3, 0): 7,
    (3, 100): 10,
    (3, 200): 8,
    (3, 300): 31,
    # COLDDESERT
    (4, 0): 3,
    (4, 100): 10,
    (4, 200): 8,
    (4, 300): 16,
    # HOTSEMIARID
    (5, 0): 0,
    (5, 100): 20,
    (5, 200): 19,
    (5, 300): 11,
    # COLDSEMIARID
    (6, 0): 0,
    (6, 100): 18,
    (6, 200): 19,
    (6, 300): 16,
    # TEMPERATEHOT
    (7, 0): 0,
    (7, 100): 2,
    (7, 200): 20,
    (7, 300): 16,
    # TEMPERATEWARM
    (8, 0): 4,
    (8, 100): 2,
    (8, 200): 20,
    (8, 300): 16,
    # TEMPERATECOLD
    (9, 0): 17,
    (9, 100): 2,
    (9, 200): 16,
    (9, 300): 16,
    # CONTINENTALHOT
    (10, 0): 1,
    (10, 100): 2,
    (10, 200): 20,
    (10, 300): 16,
    # CONTINENTALWARM
    (11, 0): 4,
    (11, 100): 20,
    (11, 200): 11,
    (11, 300): 16,
    # CONTINENTALCOLD
    (12, 0): 1,
    (12, 100): 2,
    (12, 200): 16,
    (12, 300): 16,
    # POLARTUNDRA
    (13, 0): 9,
    (13, 100): 12,
    (13, 200): 16,
    (13, 300): 16,
    # POLARARCTIC
    (14, 0): 0,
    (14, 100): 16,
    (14, 200): 16,
    (14, 300): 16,
    # SNOW
    (15, 0): 16,
    (15, 100): 16,
    (15, 200): 16,
    (15, 300): 16,
    # WATER (ocean)
    (16, 0): 15,
    (16, 100): 15,
    (16, 200): 15,
    (16, 300): 15,
}

# tree-terrain.bmp (overlay on terrain): forest-type → palette index
INDEX_MAP_TREE_TERRAIN: dict[int, int] = {
    0: 0,
    1: 1,
    2: 1,
    3: 4,
    4: 4,
    5: 22,
    6: 21,
}

# trees.bmp: forest-type → palette index
INDEX_MAP_TREES: dict[int, int] = {
    0: 0,
    1: 6,
    2: 6,
    3: 5,
    4: 3,
    5: 28,
    6: 29,
}

# trees.bmp: terrain-type string → palette index (land-use map for trees)
COLOUR_MAP_TREES: dict[str, int] = {
    "rockyHills": 5,
    "snowyHills": 5,
    "rockyMountains": 5,
    "snowyMountains": 5,
    "rockyPeaks": 5,
    "snowyPeaks": 5,
    "grassland": 5,
    "grasslandHills": 6,
    "grasslandMountains": 6,
    "desert": 2,
    "desertHills": 2,
    "desertMountains": 2,
    "forest": 6,
    "forestHills": 6,
    "forestMountains": 6,
    "savanna": 3,
    "drysavanna": 2,
    "jungle": 28,
    "tundra": 5,
    "ice": 5,
    "marsh": 5,
    "urban": 5,
    "farm": 5,
    "sea": 0,
}

# rivers.bmp: terrain-type string → palette index
COLOUR_MAP_RIVERS: dict[str, int] = {
    "land": 255,
    "river": 3,
    "river0.9": 3,
    "river0.8": 6,
    "river0.7": 6,
    "river0.6": 10,
    "river0.5": 11,
    "river0.3": 11,
    "river0.2": 11,
    "river0.1": 11,
    "sea": 254,
    "riverStart": 0,
    "riverStartTributary": 3,
    "riverEnd": 1,
}

# cities.bmp: terrain-type string → palette index
COLOUR_MAP_CITIES: dict[str, int] = {
    "sea": 15,
    "land": 1,
}


# ---------------------------------------------------------------------------
# Mod descriptor template  (== resources/hoi4/descriptor.mod)
# ---------------------------------------------------------------------------

DESCRIPTOR_MOD_TEMPLATE = """\
name="{mod_name}"
picture="thumbnail.png"
version="v1"
user_dir="{mod_name}"
replace_path="history/states"
replace_path="map/strategicregions"
replace_path="history/units"
replace_path="common/ai_strategy"
replace_path="events"
replace_path="common/on_actions"
replace_path="common/factions"
replace_path="common/factions/goals"
replace_path="common/factions/rules"
replace_path="common/factions/rules/groups"
replace_path="common/factions/templates"

tags={{
\t"Gameplay"
\t"Historical"
}}
supported_version="1.17.*"
{path_line}
remote_file_id="<ID>"
"""

REPLACE_PATHS: list[str] = [
    "history/states",
    "map/strategicregions",
    "history/units",
    "common/ai_strategy",
    "events",
    "common/on_actions",
    "common/factions",
    "common/factions/goals",
    "common/factions/rules",
    "common/factions/rules/groups",
    "common/factions/templates",
]


# ---------------------------------------------------------------------------
# State template  (== resources/hoi4/history/state.txt)
# ---------------------------------------------------------------------------
# Placeholders:
#   {id}                     ; state ID number
#   {population}             ; manpower value
#   {state_category}         ; wasteland / rural / town / city / megalopolis
#   {aluminium}..{coal}      ; resource amounts (int)
#   {victory_points}         ; victory_points = {{ ... }} block(s) or empty
#   {owner}                  ; country tag or empty (for map-only export)
#   {infrastructure}         ; 0–5
#   {air_base}               ; level int, or empty string to omit line
#   {arms_factory}           ; count int
#   {civilian_factory}       ; count int
#   {dockyards}              ; count int, or empty string to omit line
#   {naval_bases}            ; per-province naval_base blocks or empty
#   {province_list}          ; space-separated province IDs
#   {owner_block}            ; owner line or empty
#   {core_block}             ; add_core_of line or empty

STATE_TEMPLATE = """\
state={{
\tid={id}
\tname="STATE_{id}"
\tmanpower = {population}

\tstate_category = {state_category}
\t#impassable = yes
\tresources={{
\t\taluminium={aluminium}
\t\tchromium={chromium}
\t\toil={oil}
\t\trubber={rubber}
\t\tsteel={steel}
\t\ttungsten={tungsten}
\t\tcoal={coal}
\t}}

\thistory={{
\t\t{victory_points}
\t\t{owner_block}
\t\tbuildings = {{
\t\t\tinfrastructure = {infrastructure}
\t\t\t{air_base}
\t\t\tarms_factory = {arms_factory}
\t\t\tindustrial_complex = {civilian_factory}
\t\t\t{dockyards}
\t\t\t{naval_bases}
\t\t}}
\t\t{core_block}
\t}}

\tprovinces={{
\t\t{province_list}
\t}}
\tlocal_supplies=0.0
}}
"""


# ---------------------------------------------------------------------------
# Strategic region template  (== resources/hoi4/map/strategic_region.txt)
# ---------------------------------------------------------------------------
# Placeholders:
#   {id}              ; strategic region ID
#   {province_list}   ; space-separated province IDs
#   {weather_periods} ; 12 period {{ }} blocks

STRATEGIC_REGION_TEMPLATE = """\
strategic_region={{
\tid={id}
\tname="STRATEGICREGION_{id}"
\tprovinces={{
\t\t{province_list}
\t}}

\tweather={{
{weather_periods}
\t}}
}}
"""


# ---------------------------------------------------------------------------
# Country default template  (== resources/hoi4/common/country_default.txt)
# ---------------------------------------------------------------------------

COUNTRY_DEFAULT_TEMPLATE = """\


graphical_culture = {culture_gfx}
graphical_culture_2d = {culture_2d}

color = {{ {colour_rgb} }}
"""

# ---------------------------------------------------------------------------
# Colors template  (== resources/hoi4/common/colors.txt)
# ---------------------------------------------------------------------------

COLORS_TEMPLATE = (
    "{tag} = {{\n\tcolor = rgb {{ {r} {g} {b} }}\n\tcolor_ui = rgb {{ {r} {g} {b} }}\n}}\n"
)

# ---------------------------------------------------------------------------
# Bookmark template  (== resources/hoi4/common/bookmarks/the_gathering_storm.txt)
# ---------------------------------------------------------------------------
# Placeholders:
#   {major_entries}  ; repeated templateMajorTAG blocks
#   {minor_entries}  ; repeated templateMinorTAG blocks

BOOKMARK_TEMPLATE = """\
bookmarks = {{
\tbookmark = {{
\t\tname = "GATHERING_STORM_NAME"
\t\tdesc = "GATHERING_STORM_DESC"
\t\tdate = 1936.1.1.12
\t\tpicture = "GFX_select_date_1936"
\t\tdefault = yes

\t\t{major_entries}
\t\t{minor_entries}
\t\t"---"={{
\t\t\thistory = "OTHER_GATHERING_STORM_DESC"
\t\t}}
\t\teffect = {{
\t\t\trandomize_weather = 22345
\t\t}}
\t}}
}}
"""

BOOKMARK_MAJOR_ENTRY = """\
\t\t{tag}={{\n\t\t\thistory = "generic_GATHERING_STORM_DESC"\n\t\t\tideology = {ideology}\n\t\t\tideas = {{\n\t\t\t}}\n\t\t\tfocuses = {{\n\t\t\t}}\n\t\t}}"""

BOOKMARK_MINOR_ENTRY = """\
\t\t{tag}={{\n\t\t\tminor = yes\n\t\t\thistory = "generic_GATHERING_STORM_DESC"\n\t\t\tideology = {ideology}\n\t\t\tideas = {{\n\t\t\t}}\n\t\t\tfocuses = {{\n\t\t\t}}\n\t\t}}"""

# ---------------------------------------------------------------------------
# Country history template  (== resources/hoi4/history/country_template.txt)
# ---------------------------------------------------------------------------

COUNTRY_HISTORY_TEMPLATE = """\
capital = {capital}

oob = "{tag}_1936"
if = {{
\tlimit = {{
\t\tNOT = {{
\t\t\thas_dlc = "No Step Back"
\t\t}}
\t}}
\tset_oob = "{tag}_1936"
}}
if = {{
\tlimit = {{
\t\thas_dlc = "No Step Back"
\t}}
\tset_oob = "{tag}_1936_nsb"
}}
starting_train_buffer = 2
set_fuel_ratio = 0.8
starting_truck_buffer = 0.8

# Starting tech
set_technology = {{
\tbasic_train = 1
\t{generic_tech_block}
}}

### ARMOR ###
{armor_block}

### AIRFORCE ###
{air_block}

### NAVY ###
{naval_block}

{characters}

if = {{
\tlimit = {{
\t\thas_dlc = "La Resistance"
\t}}
\tset_technology = {{
\t\tarmored_car1 = 1
\t}}
}}
set_research_slots = {research_slots}
set_convoys = {convoys}
set_stability = {stability}
set_war_support = {war_support}

set_politics = {{
\truling_party = {ruling_party}
\tlast_election = "{last_election}"
\telection_frequency = 48
\telections_allowed = {elections_allowed}
}}
set_popularities = {{
\tdemocratic = {dem_pop}
\tfascism = {fas_pop}
\tcommunism = {com_pop}
\tneutrality = {neu_pop}
}}


{faction_template}
{faction_add}
"""

# ---------------------------------------------------------------------------
# Continent template  (== resources/hoi4/map/continent.txt)
# ---------------------------------------------------------------------------

CONTINENT_TEMPLATE = """\
continents = {{
\t{continent_list}

\t#Vanilla continents kept in for compatibility. Removing them breaks a lot of references to them
\teurope
\tnorth_america
\tsouth_america
\taustralia
\tafrica
\tasia
\tmiddle_east
}}
"""

# ---------------------------------------------------------------------------
# Ambient object template  (== resources/hoi4/map/ambient_object.txt)
# ---------------------------------------------------------------------------

AMBIENT_OBJECT_TEMPLATE = """\
type={{
\ttype="ambient_wind_entity"
\tuse_animation=no
\talways_visible=yes
\tobject={{
\t\tname="ambient_wind"
\t\tposition={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
}}
type={{
\ttype="ambient_water_entity"
\tuse_animation=no
\tscale=10.000000
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t205.110 10.000 1517.910
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t685.150 10.000 1008.290
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t420.090 10.000 382.670
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t1234.890 10.000 407.440
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t2541.140 10.000 370.870
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t2427.300 10.000 1655.700
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t1773.610 10.000 1295.370
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t2224.790 10.000 1268.600
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t3865.330 10.000 555.220
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t4201.620 10.000 358.560
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t5315.160 10.000 1328.670
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t5217.910 10.000 1005.380
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t5465.920 10.000 559.670
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
\tobject={{
\t\tname="ambient_water"
\t\tposition={{
\t\t\t100.000 10.000 1000.000
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
}}
type={{
\ttype="frame_border_entity"
\tuse_animation=no
\tscale=100.000000
\talways_visible=yes
\tobject={{
\t\tname="frame_border_entity_top"
\t\tposition={{
\t\t\t0.000 0.000 {yres_top}.000
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
}}
type={{
\ttype="frame_border_bottom_entity"
\tuse_animation=no
\tscale=100.000000
\talways_visible=yes
\tobject={{
\t\tname="frame_border_bottom_entity_bottom"
\t\tposition={{
\t\t\t0.000 0.000 -140.000
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
}}
type={{
\ttype="frame_border_logo_entity"
\tuse_animation=no
\tscale=300.000000
\talways_visible=yes
\tobject={{
\t\tname="frame_border_logo_entity_top"
\t\tposition={{
\t\t\t{xpos_logo}.000 0.000 {yres_logo}.000
\t\t}}
\t\trotation={{
\t\t\t0.000 0.000 0.000
\t\t}}
\t}}
}}
"""

# ---------------------------------------------------------------------------
# AI areas template  (== resources/hoi4/common/ai_areas/default.txt)
# ---------------------------------------------------------------------------

AI_AREAS_TEMPLATE = """\
areas = {{
\t# Generated continents
\t{continent_areas}

\t#Vanilla continents kept in for compatibility. Removing them breaks a lot of references to them
\teurope = {{
\t\tcontinents = {{
\t\t\teurope
\t\t}}
\t}}

\tnorth_america = {{
\t\tcontinents = {{
\t\t\tnorth_america
\t\t}}
\t}}

\tsouth_america = {{
\t\tcontinents = {{
\t\t\tsouth_america
\t\t}}
\t}}

\tafrica = {{
\t\tcontinents = {{
\t\t\tafrica
\t\t}}
\t}}

\taustralia = {{
\t\tcontinents = {{
\t\t\taustralia
\t\t}}
\t}}

\tasia = {{
\t\tcontinents = {{
\t\t\tasia
\t\t}}
\t}}

\tmiddle_east = {{
\t\tcontinents = {{
\t\t\tmiddle_east
\t\t}}
\t}}
}}
"""

# ---------------------------------------------------------------------------
# Character templates  (== resources/hoi4/common/characters/*)
# ---------------------------------------------------------------------------

CHARACTER_ENTRY_TEMPLATE = """\
\t{tag}_{name}_{lastname}={{\n\t\tname="{name} {lastname}"\n\n{character_type}\n\t}}"""

CHARACTER_LEADER_TEMPLATE = """\
\t\tcountry_leader={{\n\t\t\tideology={ideology}\n\t\t\ttraits = {{ {traits} }}\n\t\t\texpire="1965.1.1.1"\n\t\t\tid=-1\n\t\t}}"""

# ---------------------------------------------------------------------------
# Names template  (== resources/hoi4/common/names/countryNamesTemplate.txt)
# ---------------------------------------------------------------------------

COUNTRY_NAMES_TEMPLATE = """\
{tag} = {{
\tmale = {{
\t\tnames = {{ {male_names} }}
\t}}
\tfemale = {{
\t\tnames = {{ {female_names} }}
\t}}
\tsurnames = {{ {surnames} }}
\tcallsigns = {{ "Easy Kill" "The Lightning" "The Devil" "Grasshopper" "Handsome" "Moose" "Mouse" "Pebbles" "Sunshine" Demon}}

\t#Operations - treat these as keys, not strings.
\tprefix = o_operation

\toperation = {{
\t\t0 = {{ o_default_operation }}
\t}}

\tuse_geographical_default_operation_names = yes
\toffensive_operation_suffix = o_strat_offensive_default
\tdefensive_operation_suffix = o_strat_defensive_default
\tnaval_operation_suffix = o_strat_naval_default
}}
"""

# ---------------------------------------------------------------------------
# Misc map templates kept for backward compat with existing export code
# ---------------------------------------------------------------------------

# default.map ; kept for reference; HOI4 uses definition.csv primarily
# RandomParadox does NOT generate default.map for HOI4.
# We keep it because existing export code writes it.
DEFAULT_MAP = """\
definitions = "definition.csv"
provinces = "provinces.bmp"
positions = "positions.txt"
terrain = "terrain.bmp"
rivers = "rivers.bmp"
heightmap = "heightmap.bmp"
tree_definition = "trees.bmp"
continent = "continent.txt"
adjacency_rules = "adjacency_rules.txt"
adjacencies = "adjacencies.csv"
#climate = "climate.txt"
ambient_object = "ambient_object.txt"
seasons = "seasons.txt"

# Define which indices in trees.bmp palette which should count as trees for automatic terrain assignment
tree = { 3 4 7 10 }
"""

SEASONS_TXT = """\
winter = {
\tstart_date=00.12.01
\tend_date=00.02.10
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
spring = {
\tstart_date=00.03.10
\tend_date=00.04.22
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
summer = {
\tstart_date=00.05.20
\tend_date=00.09.10
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
autumn = {
\tstart_date=00.10.10
\tend_date=00.10.31
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
tree_winter = { start_date=00.11.15 end_date=00.12.01 }
tree_winter2 = { start_date=00.12.20 end_date=00.01.20 }
tree_spring = { start_date=00.02.20 end_date=00.03.01 }
tree_spring2 = { start_date=00.03.20 end_date=00.04.20 }
tree_summer = { start_date=00.05.20 end_date=00.06.01 }
tree_summer2 = { start_date=00.06.20 end_date=00.09.10 }
tree_autumn = { start_date=00.10.01 end_date=00.10.10 }
tree_autumn2 = { start_date=00.10.25 end_date=00.11.01 }
"""

# ---------------------------------------------------------------------------
# HOI4 module configuration  (== configs/default/Hearts of Iron IVModule.json)
# ---------------------------------------------------------------------------

HOI4_MODULE_CONFIG: dict = {
    "strategic_region_size": 2,
    "resource_factor": 2.0,
    "aluminium_factor": 1.0,
    "coal_factor": 1.0,
    "chromium_factor": 1.0,
    "oil_factor": 1.0,
    "rubber_factor": 1.0,
    "steel_factor": 1.0,
    "tungsten_factor": 1.0,
    "weather": {
        "base_light_rain_chance": 0.5,
        "base_heavy_rain_chance": 0.5,
        "base_mud_chance": 0.1,
        "base_blizzard_chance": 0.2,
        "base_sandstorm_chance": 0.07,
        "base_snow_chance": 0.3,
    },
    "scenario": {
        "num_countries": 60,
        "world_population_factor": 1.0,
        "industry_factor": 1.0,
    },
}


# ---------------------------------------------------------------------------
# Flat DDS terrain colormap writer
# ---------------------------------------------------------------------------


def write_flat_dds(
    path: Path,
    width: int,
    height: int,
    r: int = 127,
    g: int = 140,
    b: int = 80,
    a: int = 255,
) -> None:
    """Write an uncompressed RGBA DDS file filled with a single colour.

    Used for terrain colormap DDS files (colormap_rgb_cityemissivemask_a.dds,
    colormap_water_*.dds) when the mod has no real terrain colour data.
    The DDS is stored as uncompressed 32-bit RGBA (FOURCC=0) so no
    compression library is needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # DDS header (128 bytes, little-endian)
    # DDSD_CAPS|DDSD_HEIGHT|DDSD_WIDTH|DDSD_PIXELFORMAT = 0x81007
    # DDPF_RGB|DDPF_ALPHAPIXELS = 0x41
    header = struct.pack(
        "<4s I I I I I I I 44x I I I I I I I I I I I I I",
        b"DDS ",  # magic
        124,  # dwSize
        0x81007,  # dwFlags
        height,  # dwHeight
        width,  # dwWidth
        width * 4,  # dwPitchOrLinearSize
        0,  # dwDepth
        0,  # dwMipMapCount
        # ddspf
        32,  # dwSize
        0x41,  # dwFlags (RGB + Alpha)
        0,  # dwFourCC (uncompressed)
        32,  # dwRGBBitCount
        0x000000FF,  # R mask
        0x0000FF00,  # G mask
        0x00FF0000,  # B mask
        0xFF000000,  # A mask
        # caps
        0x1000,  # dwCaps (DDSCAPS_TEXTURE)
        0,
        0,
        0,
        0,  # Caps2-4, Reserved2
    )

    # pixel data: bottom-to-top rows, RGBA
    row = struct.pack("4B", r, g, b, a) * width
    pixels = row * height

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)
