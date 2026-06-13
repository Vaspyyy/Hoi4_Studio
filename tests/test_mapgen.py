from __future__ import annotations

import csv
from pathlib import Path
import json
import os
import tempfile

import numpy as np
import pytest
from PIL import Image

from src.mapgen.config import (
    DEFAULT_DENSITY_GREY,
    OCEAN_COLOR,
)
from src.mapgen.density_generator import create_equator_density, create_uniform_density
from src.mapgen.hoi4_export import (
    export_buildings_txt,
    export_definition_csv,
    export_province_definitions,
    export_provinces_png,
    export_railways_txt,
    export_states,
    export_strategic_regions,
    export_supply_nodes,
    export_territory_definitions,
    export_territory_history,
)
from src.mapgen.numb_gen import NumberSeries
from src.mapgen.utils import (
    clear_used_colors,
    color_from_id,
    extract_masks,
    random_seeds,
)


def _make_land_image(w: int = 100, h: int = 100) -> Image.Image:
    arr = np.full((h, w, 4), 200, dtype=np.uint8)
    ocean = np.full((h // 2, w, 4), 255, dtype=np.uint8)
    ocean[:, :, 0] = OCEAN_COLOR[0]
    ocean[:, :, 1] = OCEAN_COLOR[1]
    ocean[:, :, 2] = OCEAN_COLOR[2]
    arr[: h // 2, :] = ocean
    return Image.fromarray(arr, mode="RGBA")


class TestNumberSeries:
    def test_sequential_ids(self) -> None:
        s = NumberSeries("PRV", 1, 999999)
        ids = [s.get_id() for _ in range(10)]
        assert ids == [f"PRV{str(i).zfill(6)}" for i in range(1, 11)]

    def test_exhausted(self) -> None:
        s = NumberSeries("PRV", 1, 999999)
        assert s.get_id() == "PRV000001"
        assert s.get_id() == "PRV000002"
        assert s.get_id() == "PRV000003"
        s._next = 999999
        assert s.get_id() == "PRV999999"
        assert s.get_id() is None

    def test_custom_prefix(self) -> None:
        s = NumberSeries("T", 5, 999999)
        assert s.get_id() == "T000005"


class TestExtractMasks:
    def test_land_only(self) -> None:
        img = _make_land_image(50, 50)
        masks = extract_masks(None, img)
        assert masks["map_h"] == 50
        assert masks["map_w"] == 50
        assert masks["sea_mask"].shape == (50, 50)
        assert masks["land_mask"].shape == (50, 50)
        assert masks["lake_mask"].shape == (50, 50)
        assert masks["boundary_mask"] is None

    def test_no_images_raises(self) -> None:
        with pytest.raises(ValueError):
            extract_masks(None, None)


class TestRandomSeeds:
    def test_count(self) -> None:
        mask = np.ones((50, 50), dtype=bool)
        seeds = random_seeds(mask, 10, rng_seed=42)
        assert len(seeds) == 10

    def test_empty_mask(self) -> None:
        mask = np.zeros((50, 50), dtype=bool)
        seeds = random_seeds(mask, 10)
        assert seeds == []

    def test_zero_points(self) -> None:
        mask = np.ones((50, 50), dtype=bool)
        seeds = random_seeds(mask, 0)
        assert seeds == []


class TestColorFromId:
    def test_uniqueness(self) -> None:
        clear_used_colors()
        colors = {color_from_id(i, "land") for i in range(1000)}
        assert len(colors) == 1000

    def test_ocean_range(self) -> None:
        clear_used_colors()
        r, g, b = color_from_id(0, "ocean")
        assert 0 <= r < 60
        assert 0 <= g < 80
        assert 100 <= b < 180


class TestDensityGenerator:
    def test_uniform_dimensions(self) -> None:
        img = create_uniform_density(200, 100)
        assert img.size == (200, 100)
        assert img.mode == "L"
        arr = np.array(img)
        assert arr.mean() == DEFAULT_DENSITY_GREY

    def test_equator_dimensions(self) -> None:
        img = create_equator_density(200, 100)
        assert img.size == (200, 100)
        arr = np.array(img)
        center = arr[50, 0]
        edge = arr[0, 0]
        assert center < edge


class TestExportDefinitionCsv:
    def test_format_no_header_null_province(self) -> None:
        """definition.csv has NO header row; first row is province 0."""
        data = [
            {"province_id": "PRV000001", "R": 100, "G": 200, "B": 50, "province_type": "land"},
            {"province_id": "PRV000002", "R": 150, "G": 75, "B": 200, "province_type": "land"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path)
            with open(path) as f:
                reader = csv.reader(f, delimiter=";")
                rows = list(reader)
            # row 0: null province [0,0,0,0,land,false,unknown,0]
            assert rows[0] == ["0", "0", "0", "0", "land", "false", "unknown", "0"]
            # row 1: first real province
            assert rows[1][0] == "PRV000001"
            assert rows[1][1] == "100"
            assert rows[1][2] == "200"
            assert rows[1][3] == "50"
            assert rows[1][4] == "land"

    def test_coastal_true(self) -> None:
        """Coastal provinces get is_coastal=true."""
        data = [
            {"province_id": 1, "R": 100, "G": 200, "B": 50, "province_type": "land"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path, coastal={1})
            with open(path) as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[1][5] == "true"

    def test_coastal_false(self) -> None:
        """Non-coastal provinces get is_coastal=false."""
        data = [
            {"province_id": 1, "R": 100, "G": 200, "B": 50, "province_type": "land"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path, coastal=set())
            with open(path) as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[1][5] == "false"

    def test_ocean_maps_to_sea(self) -> None:
        """Internal 'ocean' type maps to HOI4 'sea' type."""
        data = [
            {"province_id": 1, "R": 0, "G": 0, "B": 0, "province_type": "ocean"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path)
            with open(path) as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[1][4] == "sea"
            assert rows[1][6] == "ocean"
            assert rows[1][7] == "0"

    def test_lake_maps_correctly(self) -> None:
        """Lake provinces get type 'lake', terrain 'lakes', continent 0."""
        data = [
            {"province_id": 1, "R": 0, "G": 0, "B": 0, "province_type": "lake"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path)
            with open(path) as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[1][4] == "lake"
            assert rows[1][6] == "lakes"
            assert rows[1][7] == "0"

    def test_land_continent_is_one(self) -> None:
        """Land provinces get continent 1."""
        data = [
            {"province_id": 1, "R": 100, "G": 200, "B": 50, "province_type": "land"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path)
            with open(path) as f:
                rows = list(csv.reader(f, delimiter=";"))
            assert rows[1][7] == "1"


class TestExportTerritoryDefinitions:
    def test_json_format(self) -> None:
        data = [
            {
                "territory_id": "TRT000001",
                "territory_type": "land",
                "R": 100,
                "G": 200,
                "B": 50,
                "x": 10.5,
                "y": 20.3,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "terr.json")
            export_territory_definitions(data, path, fmt="json")
            with open(path) as f:
                obj = json.load(f)
            assert "TRT000001" in obj
            assert obj["TRT000001"]["territory_type"] == "land"


class TestExportProvinceDefinitions:
    def test_with_terrain(self) -> None:
        data = [
            {
                "province_id": "PRV000001",
                "province_type": "land",
                "R": 100,
                "G": 200,
                "B": 50,
                "x": 10.5,
                "y": 20.3,
                "province_terrain": "plains",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prov.json")
            export_province_definitions(data, path, fmt="json")
            with open(path) as f:
                obj = json.load(f)
            assert obj["PRV000001"]["province_terrain"] == "plains"


class TestExportProvincesPng:
    def test_saves_file(self) -> None:
        img = Image.new("RGB", (50, 50), (100, 200, 50))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "provinces.png")
            export_provinces_png(img, path)
            assert os.path.exists(path)


class TestExportTerritoryHistory:
    def test_csv_format(self) -> None:
        data = [
            {
                "territory_id": "TRT000001",
                "province_ids": ["PRV000001", "PRV000002"],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.csv")
            export_territory_history(data, path, fmt="csv")
            with open(path) as f:
                reader = csv.reader(f, delimiter=";")
                rows = list(reader)
            assert rows[0] == ["id", "provinces"]
            assert rows[1][1] == "PRV000001,PRV000002"


# ---------------------------------------------------------------------------
# buildings.txt
# ---------------------------------------------------------------------------

_land_province = {"province_id": 1, "province_type": "land", "x": 10.0, "y": 20.0}


def _territory(tid: int, pids: list[int]) -> dict:
    return {"territory_id": tid, "territory_type": "land", "province_ids": pids}


class TestExportBuildingsTxt:
    def test_field_order_state_id_first(self) -> None:
        """Output: state_id;type;x;z;y;rotation;province_id."""
        pd = [{"province_id": 1, "province_type": "land", "x": 10.5, "y": 20.3}]
        td = [_territory(5, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path, coastal={1})
            lines = Path(path).read_text().strip().split("\n")
        # coastal province and territory capital: 4 entries
        assert len(lines) == 4
        for line in lines:
            parts = line.split(";")
            assert parts[0] == "5"  # state_id first
            assert parts[6] == "1"  # province_id last

    def test_no_infrastructure(self) -> None:
        """Infrastructure is NOT a valid building type in buildings.txt."""
        pd = [{"province_id": 1, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text()
        assert "infrastructure" not in content

    def test_ocean_skipped(self) -> None:
        pd = [
            {"province_id": 1, "province_type": "ocean", "x": 10.0, "y": 20.0},
            {"province_id": 2, "province_type": "land", "x": 10.0, "y": 20.0},
        ]
        td = [_territory(1, [1, 2])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text()
        assert "1;" not in content  # ocean province 1 not written

    def test_lake_skipped(self) -> None:
        pd = [
            {"province_id": 1, "province_type": "lake", "x": 10.0, "y": 20.0},
        ]
        td = [_territory(1, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text()
        assert content.strip() == ""

    def test_state_id_zero_skipped(self) -> None:
        """Province not in any land territory (state_id=0) produces nothing."""
        pd = [{"province_id": 99, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1])]  # province 99 not in territory
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text()
        assert content.strip() == ""

    def test_coastal_gets_naval_bunker(self) -> None:
        pd = [{"province_id": 1, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path, coastal={1})
            content = Path(path).read_text()
        assert "naval_base_spawn" in content
        assert "coastal_bunker" in content

    def test_capital_gets_factories(self) -> None:
        pd = [{"province_id": 1, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text()
        assert "arms_factory" in content
        assert "industrial_complex" in content

    def test_non_capital_non_coastal_gets_nothing(self) -> None:
        """Non-capital, non-coastal land province produces zero rows."""
        pd = [{"province_id": 2, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1, 2])]  # province 2 is not the capital (first in list)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path)
            content = Path(path).read_text().strip()
        assert content == ""

    def test_z_and_rotation_constants(self) -> None:
        pd = [{"province_id": 1, "province_type": "land", "x": 10.0, "y": 20.0}]
        td = [_territory(1, [1])]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buildings.txt")
            export_buildings_txt(pd, td, path, coastal={1})
            content = Path(path).read_text()
        for line in content.strip().split("\n"):
            parts = line.split(";")
            assert parts[3] == "10.00"  # z
            assert parts[5] == "0.00"  # rotation


# ---------------------------------------------------------------------------
# supply_nodes.txt
# ---------------------------------------------------------------------------


class TestExportSupplyNodes:
    def test_format_level_pid(self) -> None:
        """Format: 1 {province_id}, one per territory center."""
        td = [
            {"territory_id": 10, "province_ids": [5, 6, 7]},
            {"territory_id": 20, "province_ids": [12, 13]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "supply_nodes.txt")
            export_supply_nodes([], td, path)
            lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == "1 5"
        assert lines[1] == "1 12"

    def test_only_territory_centers(self) -> None:
        """Non-first provinces in a territory don't get supply nodes."""
        td = [{"territory_id": 10, "province_ids": [5, 6, 7]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "supply_nodes.txt")
            export_supply_nodes([], td, path)
            content = Path(path).read_text()
        assert "6" not in content.split()
        assert "7" not in content.split()

    def test_empty_territory_skipped(self) -> None:
        td = [
            {"territory_id": 10, "province_ids": []},
            {"territory_id": 20, "province_ids": [42]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "supply_nodes.txt")
            export_supply_nodes([], td, path)
            content = Path(path).read_text().strip()
        assert content == "1 42"

    def test_sorted_output(self) -> None:
        td = [
            {"territory_id": 30, "province_ids": [300]},
            {"territory_id": 10, "province_ids": [100]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "supply_nodes.txt")
            export_supply_nodes([], td, path)
            lines = Path(path).read_text().strip().split("\n")
        assert lines[0] == "1 100"
        assert lines[1] == "1 300"


# ---------------------------------------------------------------------------
# railways.txt
# ---------------------------------------------------------------------------


class TestExportRailwaysTxt:
    def test_water_excluded(self) -> None:
        """No railways through water provinces."""
        pd = [
            {"province_id": 1, "province_type": "land"},
            {"province_id": 2, "province_type": "ocean"},
            {"province_id": 3, "province_type": "land"},
        ]
        td = [
            {"territory_id": 1, "territory_type": "land", "province_ids": [1]},
            {"territory_id": 2, "territory_type": "land", "province_ids": [3]},
        ]
        # Only adjacency is through water province 2 — no land path
        adj = {(1, 2), (2, 3)}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "railways.txt")
            export_railways_txt(path, pd, td, adj)
            content = Path(path).read_text().strip()
        assert content == ""

    def test_empty_when_no_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "railways.txt")
            export_railways_txt(path)
            content = Path(path).read_text().strip()
        assert content == ""

    def test_sea_territory_skipped(self) -> None:
        """Sea territory centers don't participate in railway network."""
        pd = [
            {"province_id": 1, "province_type": "land"},
            {"province_id": 2, "province_type": "ocean"},
        ]
        # territory 2 is sea — should be ignored
        td = [
            {"territory_id": 1, "territory_type": "land", "province_ids": [1]},
            {"territory_id": 2, "territory_type": "sea", "province_ids": [2]},
        ]
        adj = {(1, 2)}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "railways.txt")
            export_railways_txt(path, pd, td, adj)
            content = Path(path).read_text().strip()
        assert content == ""


# ---------------------------------------------------------------------------
# strategic regions
# ---------------------------------------------------------------------------


class TestExportStrategicRegions:
    def test_creates_file_per_territory(self) -> None:
        pd = [
            {"province_id": 1, "territory_id": 5},
            {"province_id": 2, "territory_id": 5},
            {"province_id": 3, "territory_id": 8},
        ]
        td = [
            {"territory_id": 5},
            {"territory_id": 8},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "strategicregions")
            export_strategic_regions(td, pd, out_dir)
            files = sorted(os.listdir(out_dir))
        assert files == ["5-Territory_5.txt", "8-Territory_8.txt"]

    def test_file_contains_province_list(self) -> None:
        pd = [{"province_id": 1, "territory_id": 5}]
        td = [{"territory_id": 5}]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "strategicregions")
            export_strategic_regions(td, pd, out_dir)
            content = Path(out_dir, "5-Territory_5.txt").read_text()
        assert "provinces={" in content
        assert "1" in content

    def test_file_contains_weather_periods(self) -> None:
        pd = [{"province_id": 1, "territory_id": 5}]
        td = [{"territory_id": 5}]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "strategicregions")
            export_strategic_regions(td, pd, out_dir)
            content = Path(out_dir, "5-Territory_5.txt").read_text()
        assert "weather={" in content
        assert "period={" in content

    def test_skips_territory_with_no_provinces(self) -> None:
        pd = [{"province_id": 1, "territory_id": 5}]
        td = [
            {"territory_id": 5},
            {"territory_id": 99},  # no provinces
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "strategicregions")
            result = export_strategic_regions(td, pd, out_dir)
            files = os.listdir(out_dir)
        assert len(files) == 1
        assert len(result) == 1


# ---------------------------------------------------------------------------
# states
# ---------------------------------------------------------------------------


class TestExportStates:
    def test_creates_file_per_land_territory(self) -> None:
        td = [
            {"territory_id": 1, "territory_type": "land", "province_ids": [10]},
            {"territory_id": 2, "territory_type": "ocean", "province_ids": [20]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root)
            state_dir = mod_root / "history" / "states"
            files = sorted(state_dir.iterdir())
        assert [f.name for f in files] == ["1.txt"]

    def test_state_contains_victory_point(self) -> None:
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": [42, 43]}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root)
            content = (mod_root / "history/states/1.txt").read_text()
        assert "victory_points = { 42 1 }" in content

    def test_state_contains_province_list(self) -> None:
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": [5, 8, 3]}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root)
            content = (mod_root / "history/states/1.txt").read_text()
        assert "provinces={" in content

    def test_population_auto_computed(self) -> None:
        """25000 per province by default."""
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": list(range(4))}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root)
            content = (mod_root / "history/states/1.txt").read_text()
        assert "manpower = 100000" in content

    def test_state_category_scaled(self) -> None:
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": list(range(1))}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root)
            content = (mod_root / "history/states/1.txt").read_text()
        assert "state_category = wasteland" in content

    def test_coastal_gets_naval_base_in_buildings(self) -> None:
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": [10, 11]}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root, coastal={10})
            content = (mod_root / "history/states/1.txt").read_text()
        assert "naval_base" in content
        assert "10 = {" in content

    def test_non_coastal_no_naval_base(self) -> None:
        td = [{"territory_id": 1, "territory_type": "land", "province_ids": [10]}]
        with tempfile.TemporaryDirectory() as tmp:
            mod_root = Path(tmp) / "mod"
            export_states(td, mod_root, coastal=set())
            content = (mod_root / "history/states/1.txt").read_text()
        assert "naval_base" not in content
