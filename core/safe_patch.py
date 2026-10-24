"""
PluginReaper — Safe patch helpers for common "I wish this plugin had X" edits.

Generates ready-to-paste Luau snippets and can inject a toolbar button stub
into the main entry script without destroying existing logic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple


TOOLBAR_BUTTON_SNIPPET = '''
-- [PluginReaper] Added toolbar button
do
	local toolbar = plugin:CreateToolbar("{toolbar_name}")
	local button = toolbar:CreateButton("{button_name}", "{tooltip}", "{icon}")
	button.Click:Connect(function()
		-- TODO: your feature here
		print("[PluginReaper] {button_name} clicked")
	end)
end
'''.lstrip()

SETTING_SNIPPET = '''
-- [PluginReaper] Setting helpers
local function getSetting(key, default)
	local ok, value = pcall(function()
		return plugin:GetSetting(key)
	end)
	if ok and value ~= nil then
		return value
	end
	return default
end

local function setSetting(key, value)
	pcall(function()
		plugin:SetSetting(key, value)
	end)
end
'''.lstrip()

DOCK_WIDGET_SNIPPET = '''
-- [PluginReaper] Dock widget stub
do
	local info = DockWidgetPluginGuiInfo.new(
		Enum.InitialDockState.Float,
		false, -- enabled
		false, -- override previous state
		400, 300, -- floating size
		200, 150  -- min size
	)
	local widget = plugin:CreateDockWidgetPluginGui("{widget_id}", info)
	widget.Title = "{title}"
	widget.Name = "{widget_id}"

	local frame = Instance.new("Frame")
	frame.Size = UDim2.fromScale(1, 1)
	frame.BackgroundColor3 = Color3.fromRGB(40, 40, 40)
	frame.Parent = widget

	-- TODO: build UI under `frame`
end
'''.lstrip()


def find_entry_scripts(root: Path) -> List[Path]:
    root = Path(root)
    candidates: List[Path] = []
    for name in ("init.server.luau", "init.luau", "init.server.lua", "init.lua"):
        for p in root.rglob(name):
            candidates.append(p)
    # also top-level .server.luau
    for p in root.glob("*.server.luau"):
        candidates.append(p)
    for p in root.glob("*/*.server.luau"):
        candidates.append(p)
    # unique preserve order
    seen = set()
    out = []
    for p in candidates:
        s = str(p.resolve())
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


def append_snippet(script_path: Path, snippet: str) -> bool:
    text = script_path.read_text(encoding="utf-8", errors="replace")
    marker = snippet.strip().splitlines()[0] if snippet.strip() else ""
    if marker and marker in text:
        return False  # already present
    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + snippet
    if not text.endswith("\n"):
        text += "\n"
    script_path.write_text(text, encoding="utf-8")
    return True


def inject_toolbar_button(
    root: Path,
    *,
    toolbar_name: str = "MyTools",
    button_name: str = "MyFeature",
    tooltip: str = "Custom feature",
    icon: str = "rbxassetid://0",
) -> Optional[Path]:
    entries = find_entry_scripts(root)
    if not entries:
        return None
    target = entries[0]
    snip = TOOLBAR_BUTTON_SNIPPET.format(
        toolbar_name=toolbar_name,
        button_name=button_name,
        tooltip=tooltip,
        icon=icon,
    )
    if append_snippet(target, snip):
        return target
    return target  # already had it


def inject_settings_helpers(root: Path) -> Optional[Path]:
    entries = find_entry_scripts(root)
    if not entries:
        return None
    target = entries[0]
    if append_snippet(target, SETTING_SNIPPET):
        return target
    return target


def inject_dock_widget(
    root: Path,
    *,
    widget_id: str = "PluginReaperWidget",
    title: str = "Custom Panel",
) -> Optional[Path]:
    entries = find_entry_scripts(root)
    if not entries:
        return None
    target = entries[0]
    snip = DOCK_WIDGET_SNIPPET.format(widget_id=widget_id, title=title)
    if append_snippet(target, snip):
        return target
    return target


def list_snippets() -> dict:
    return {
        "toolbar_button": "Add plugin toolbar + button with Click handler",
        "settings": "GetSetting / SetSetting helpers",
        "dock_widget": "Floating dock widget + root Frame stub",
    }
