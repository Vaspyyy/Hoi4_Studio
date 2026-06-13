from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from src.utils import (
    _open_image,
    _have_magick,
    nuclear_delete_mod,
    import_flag_to_mod,
)


class TestOpenImage:
    def test_open_png(self, tmp_path):
        img_path = tmp_path / "test.png"
        Image.new("RGB", (10, 10), (255, 0, 0)).save(img_path)
        result = _open_image(img_path)
        assert result.size == (10, 10)
        result.close()

    def test_open_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _open_image(tmp_path / "missing.png")

    def test_svg_without_magick_raises(self, tmp_path):
        svg_path = tmp_path / "test.svg"
        svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        with patch("src.utils._have_magick", return_value=False):
            with pytest.raises(RuntimeError, match="ImageMagick"):
                _open_image(svg_path)


class TestHaveMagick:
    def test_found(self):
        with patch("shutil.which", return_value="/usr/bin/magick"):
            assert _have_magick() is True

    def test_not_found(self):
        with patch("shutil.which", return_value=None):
            assert _have_magick() is False


class TestNuclearDeleteMod:
    def test_refuses_suspicious_path(self, tmp_path):
        shallow = Path("/tmp/hoi4_test_shallow_mod")
        shallow.mkdir(exist_ok=True)
        user_mods = tmp_path / "mods"
        user_mods.mkdir()
        try:
            with pytest.raises(ValueError, match="Refusing to delete"):
                nuclear_delete_mod(shallow, user_mods)
        finally:
            shallow.rmdir()

    def test_deletes_inside_user_mods(self, tmp_path):
        user_mods = tmp_path / "user_mods"
        mod_root = user_mods / "my_mod"
        mod_root.mkdir(parents=True)
        (mod_root / "file.txt").write_text("data")
        nuclear_delete_mod(mod_root, user_mods)
        assert not mod_root.exists()

    def test_deletes_deep_path(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "file.txt").write_text("data")
        nuclear_delete_mod(deep, tmp_path / "mods")
        assert not deep.exists()

    def test_deletes_descriptor(self, tmp_path):
        user_mods = tmp_path / "user_mods"
        mod_root = user_mods / "my_mod"
        mod_root.mkdir(parents=True)
        desc = user_mods / "my_mod.mod"
        desc.write_text("name=MyMod")
        nuclear_delete_mod(mod_root, user_mods, descriptor_filename="my_mod.mod")
        assert not mod_root.exists()
        assert not desc.exists()

    def test_no_descriptor_param(self, tmp_path):
        user_mods = tmp_path / "user_mods"
        mod_root = user_mods / "my_mod"
        mod_root.mkdir(parents=True)
        nuclear_delete_mod(mod_root, user_mods)
        assert not mod_root.exists()

    def test_nonexistent_mod_root(self, tmp_path):
        user_mods = tmp_path / "user_mods"
        mod_root = user_mods / "nonexistent"
        user_mods.mkdir(parents=True)
        nuclear_delete_mod(mod_root, user_mods)
        assert not mod_root.exists()


class TestImportFlagToMod:
    def test_creates_tga_sizes(self, tmp_path):
        src = tmp_path / "flag.png"
        Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        import_flag_to_mod(mod_root, "ABC", src)
        assert (mod_root / "gfx/flags/ABC.tga").exists()
        assert (mod_root / "gfx/flags/medium/ABC.tga").exists()
        assert (mod_root / "gfx/flags/small/ABC.tga").exists()

    def test_vanilla_override_creates_all_suffixes(self, tmp_path):
        src = tmp_path / "flag.png"
        Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        import_flag_to_mod(mod_root, "GER", src, vanilla_override=True)
        for suffix in ["", "_neutrality", "_democratic", "_fascism", "_communism"]:
            assert (mod_root / f"gfx/flags/GER{suffix}.tga").exists()
            assert (mod_root / f"gfx/flags/medium/GER{suffix}.tga").exists()
            assert (mod_root / f"gfx/flags/small/GER{suffix}.tga").exists()


class TestImportPortraitToMod:
    def test_without_magick_raises(self, tmp_path):
        from src.utils import import_portrait_to_mod

        src = tmp_path / "portrait.png"
        Image.new("RGBA", (200, 300), (0, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        with patch("src.utils._have_magick", return_value=False):
            with pytest.raises(RuntimeError, match="ImageMagick"):
                import_portrait_to_mod(mod_root, "GER", "leader_1", src)

    def test_creates_png_and_converts(self, tmp_path):
        from src.utils import import_portrait_to_mod

        src = tmp_path / "portrait.png"
        Image.new("RGBA", (200, 300), (0, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("src.utils._have_magick", return_value=True), patch(
            "subprocess.run", return_value=mock_result
        ) as mock_run:
            dds_path = mod_root / "gfx/leaders/GER/leader_1.dds"
            dds_path.parent.mkdir(parents=True, exist_ok=True)
            dds_path.write_bytes(b"DDS!")
            result = import_portrait_to_mod(mod_root, "GER", "leader_1", src)
            assert result == dds_path
            mock_run.assert_called_once()

    def test_magick_failure_raises(self, tmp_path):
        from src.utils import import_portrait_to_mod

        src = tmp_path / "portrait.png"
        Image.new("RGBA", (200, 300), (0, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "conversion failed"
        with patch("src.utils._have_magick", return_value=True), patch(
            "subprocess.run", return_value=mock_result
        ):
            with pytest.raises(RuntimeError, match="DDS conversion failed"):
                import_portrait_to_mod(mod_root, "GER", "leader_1", src)

    def test_magick_success_but_no_dds_raises(self, tmp_path):
        from src.utils import import_portrait_to_mod

        src = tmp_path / "portrait.png"
        Image.new("RGBA", (200, 300), (0, 0, 0, 255)).save(src)
        mod_root = tmp_path / "mod"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("src.utils._have_magick", return_value=True), patch(
            "subprocess.run", return_value=mock_result
        ):
            with pytest.raises(RuntimeError, match="DDS conversion failed"):
                import_portrait_to_mod(mod_root, "GER", "leader_1", src)
