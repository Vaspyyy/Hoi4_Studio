from __future__ import annotations

import csv
import json
from pathlib import Path

# TODO: all export functions lack try/except around file writes; a disk error
# propagates silently to the UI thread via the worker's catch-all.


def export_definition_csv(province_data: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["province", "red", "green", "blue", "x", "y"])
        for d in province_data:
            w.writerow(
                [
                    d["province_id"],
                    d["R"],
                    d["G"],
                    d["B"],
                    round(d["x"]),
                    round(d["y"]),
                ]
            )


def export_provinces_png(province_image, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    province_image.save(path)


def export_territory_definitions(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        data = {}
        for d in metadata:
            data[d["territory_id"]] = {
                "territory_type": d["territory_type"],
                "R": d["R"],
                "G": d["G"],
                "B": d["B"],
                "x": round(d["x"], 2),
                "y": round(d["y"], 2),
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id", "territory_type", "R", "G", "B", "x", "y"])
            for d in metadata:
                w.writerow(
                    [
                        d["territory_id"],
                        d["territory_type"],
                        d["R"],
                        d["G"],
                        d["B"],
                        round(d["x"], 2),
                        round(d["y"], 2),
                    ]
                )


def export_province_definitions(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    has_terrain = any("province_terrain" in d for d in metadata)

    if fmt == "json":
        data = {}
        for d in metadata:
            entry = {
                "province_type": d["province_type"],
                "R": d["R"],
                "G": d["G"],
                "B": d["B"],
                "x": round(d["x"], 2),
                "y": round(d["y"], 2),
            }
            if has_terrain:
                entry["province_terrain"] = d.get("province_terrain", "unknown")
            data[d["province_id"]] = entry
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            header = ["id", "province_type", "R", "G", "B", "x", "y"]
            if has_terrain:
                header.append("province_terrain")
            w.writerow(header)
            for d in metadata:
                row = [
                    d["province_id"],
                    d["province_type"],
                    d["R"],
                    d["G"],
                    d["B"],
                    round(d["x"], 2),
                    round(d["y"], 2),
                ]
                if has_terrain:
                    row.append(d.get("province_terrain", "unknown"))
                w.writerow(row)


def export_territory_history(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        data = {}
        for d in metadata:
            data[d["territory_id"]] = {
                "provinces": d.get("province_ids", []),
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id", "provinces"])
            for d in metadata:
                provinces = ",".join(d.get("province_ids", []))
                w.writerow([d["territory_id"], provinces])
