from __future__ import annotations

import csv
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
    export_definition_csv,
    export_province_definitions,
    export_provinces_png,
    export_territory_definitions,
    export_territory_history,
)
from src.mapgen.numb_gen import IntegerSeries, NumberSeries
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


class TestIntegerSeries:
    def test_sequential(self) -> None:
        s = IntegerSeries(1, 5)
        assert [s.get_id() for _ in range(5)] == [1, 2, 3, 4, 5]

    def test_exhausted(self) -> None:
        s = IntegerSeries(1, 2)
        assert s.get_id() == 1
        assert s.get_id() == 2
        assert s.get_id() is None


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
    def test_format(self) -> None:
        data = [
            {"province_id": "PRV000001", "R": 100, "G": 200, "B": 50, "x": 10.5, "y": 20.3},
            {"province_id": "PRV000002", "R": 150, "G": 75, "B": 200, "x": 30.7, "y": 40.1},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "definition.csv")
            export_definition_csv(data, path)
            with open(path) as f:
                reader = csv.reader(f, delimiter=";")
                rows = list(reader)
            assert rows[0] == ["province", "red", "green", "blue", "x", "y"]
            assert rows[1][0] == "PRV000001"
            assert rows[1][1] == "100"


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
