from __future__ import annotations

import importlib

_lazy = {
    "WelcomeTab": ".welcome_tab",
    "ProjectTab": ".project_tab",
    "CountryTab": ".country_tab",
    "StatesTab": ".states_tab",
    "StatePropertiesTab": ".state_properties_tab",
    "StateBrowserTab": ".state_browser_tab",
    "EventBuilderTab": ".event_builder_tab",
    "FocusTab": ".focus_tab",
    "IdeasTab": ".ideas_tab",
    "LocalizationManagerTab": ".localization_tab",
    "MapGeneratorTab": ".map_generator_tab",
    "BookmarkTab": ".bookmark_tab",
}

__all__ = list(_lazy.keys())


def __getattr__(name: str):
    if name in _lazy:
        mod = importlib.import_module(_lazy[name], __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
