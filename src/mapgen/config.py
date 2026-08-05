LAND_PROVINCES_MIN = 100
LAND_PROVINCES_MAX = 100000
LAND_PROVINCES_DEFAULT = 3000
LAND_PROVINCES_TICK = 200
LAND_PROVINCES_STEP = 100

OCEAN_PROVINCES_MIN = 10
OCEAN_PROVINCES_MAX = 10000
OCEAN_PROVINCES_DEFAULT = 300
OCEAN_PROVINCES_TICK = 20
OCEAN_PROVINCES_STEP = 10

# Territories become states and strategic regions; provinces subdivide them.
# Defaults keep roughly a 10:1 province-to-territory ratio so the province step
# actually subdivides something — matching them 1:1 makes it a no-op.
# (Vanilla HOI4 is ~13,000 provinces across ~1,000 states.)
LAND_TERRITORIES_MIN = 100
LAND_TERRITORIES_MAX = 10000
LAND_TERRITORIES_DEFAULT = 300
LAND_TERRITORIES_TICK = 200
LAND_TERRITORIES_STEP = 100

OCEAN_TERRITORIES_MIN = 10
OCEAN_TERRITORIES_MAX = 1000
OCEAN_TERRITORIES_DEFAULT = 30
OCEAN_TERRITORIES_TICK = 20
OCEAN_TERRITORIES_STEP = 10

OCEAN_COLOR = (5, 20, 18)
LAKE_COLOR = (0, 255, 0)
BOUNDARY_COLOR = (0, 0, 0)

MAX_IMAGE_PIXELS = 300000000

LLOYD_ITERATIONS = 4
JAGGED_BORDER_AMPLITUDE = 0.12

# Seeding is opt-in; when off, generation stays random on every run.
DEFAULT_SEED = 1

DEFAULT_DENSITY_GREY = 128
DENSITY_STRENGTH_DEFAULT = 20
DENSITY_STRENGTH_MIN = 0
DENSITY_STRENGTH_MAX = 50
DENSITY_STRENGTH_TICK = 5
DENSITY_STRENGTH_STEP = 1

LAND_TERRAIN_TYPES: dict[str, tuple[int, int, int]] = {
    "forest": (89, 199, 85),
    "hills": (248, 255, 153),
    "mountain": (157, 192, 208),
    "plains": (255, 129, 66),
    "urban": (120, 120, 120),
    "jungle": (127, 191, 0),
    "marsh": (76, 96, 35),
    "desert": (255, 127, 0),
}

NAVAL_TERRAIN_TYPES: dict[str, tuple[int, int, int]] = {
    "deep_ocean": (2, 38, 150),
    "shallow_sea": (56, 118, 217),
    "fjords": (75, 162, 198),
}

LAKE_TERRAIN_TYPES: dict[str, tuple[int, int, int]] = {
    "lakes": (58, 91, 255),
}

TERRAIN_TYPES = {**LAND_TERRAIN_TYPES, **NAVAL_TERRAIN_TYPES, **LAKE_TERRAIN_TYPES}

DEFAULT_TERRAIN_LAND = "plains"
DEFAULT_TERRAIN_OCEAN = "deep_ocean"
DEFAULT_TERRAIN_LAKE = "lakes"
