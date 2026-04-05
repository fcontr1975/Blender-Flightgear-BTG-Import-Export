import json
import os
import re
import shutil
from xml.sax.saxutils import escape as _xml_escape

try:
    import bpy  # type: ignore[import-not-found]
except ModuleNotFoundError:
    bpy = None

DEFAULT_TEXTURE_ROOT = "/usr/share/games/flightgear/Textures/"
ADDON_ID = "io_scene_flightgear_btg"

TEXTURE_ALIASES = {
    "airport": ["airport"],
    "default": ["grass", "airport"],
    "grass": ["grass"],
    "grasscover": ["grass"],
    "grassland": ["grass"],
    "intermittentstream": ["waterlake"],
    "stream": ["waterlake"],
    "canal": ["waterlake"],
    "lake": ["waterlake", "frozenlake"],
    "road": ["asphalt", "gravel"],
    "freeway": ["asphalt"],
    "railroad": ["gravel", "darkgravel"],
    "drycrop": ["drycrop"],
    "mixedcrop": ["mixedcrop"],
    "irrcroppasturecover": ["irrcrop", "cropgrass"],
    "irrcrop": ["irrcrop"],
    "deciduousforest": ["deciduous", "forest"],
    "evergreenforest": ["evergreen", "coniferousforest"],
    "scrub": ["shrub", "scrub"],
    "scrubcover": ["shrub", "scrub"],
    "urban": ["industrial", "city"],
    "pctiedown": ["asphalt", "carpark"],
}

FALLBACK_COLORS = {
    "airport": (0.35, 0.35, 0.35),
    "default": (0.40, 0.55, 0.30),
    "grass": (0.35, 0.55, 0.25),
    "grasscover": (0.35, 0.55, 0.25),
    "grassland": (0.45, 0.60, 0.30),
    "intermittentstream": (0.15, 0.30, 0.50),
    "stream": (0.15, 0.30, 0.50),
    "canal": (0.12, 0.28, 0.45),
    "lake": (0.10, 0.22, 0.40),
    "road": (0.22, 0.22, 0.22),
    "freeway": (0.18, 0.18, 0.18),
    "railroad": (0.25, 0.22, 0.20),
    "drycrop": (0.62, 0.56, 0.30),
    "mixedcrop": (0.50, 0.58, 0.28),
    "irrcroppasturecover": (0.42, 0.62, 0.24),
    "irrcrop": (0.42, 0.62, 0.24),
    "deciduousforest": (0.18, 0.38, 0.18),
    "evergreenforest": (0.12, 0.28, 0.14),
    "scrub": (0.42, 0.45, 0.22),
    "scrubcover": (0.42, 0.45, 0.22),
    "urban": (0.45, 0.45, 0.45),
    "pctiedown": (0.32, 0.32, 0.32),
}

_TEXTURE_INDEX_CACHE = {}
_MATERIAL_OVERRIDE_CACHE = {}
_MATERIALS_XML_LIBRARY_CACHE = {}
_MATERIALS_ROOT_LIBRARY_CACHE = {}

_MANAGED_MATERIALS_BEGIN = "<!-- BEGIN BFG EXPORTER MATERIALS -->"
_MANAGED_MATERIALS_END = "<!-- END BFG EXPORTER MATERIALS -->"

FG_MATERIAL_PRESET_DEFAULTS = {
    "GENERIC_TERRAIN": {
        "effect": "Effects/terrain-default",
        "xsize": 1000.0,
        "ysize": 1000.0,
        "wrapu": True,
        "wrapv": True,
        "override_solid": False,
        "solid": True,
        "override_physics": False,
        "friction_factor": 0.8,
        "rolling_friction": 0.05,
        "bumpiness": 0.05,
        "load_resistance": 100000.0,
    },
    "RUNWAY_TAXIWAY": {
        "effect": "Effects/runway",
        "xsize": 75.0,
        "ysize": 75.0,
        "wrapu": True,
        "wrapv": True,
        "override_solid": True,
        "solid": True,
        "override_physics": True,
        "friction_factor": 0.8,
        "rolling_friction": 0.05,
        "bumpiness": 0.05,
        "load_resistance": 100000.0,
    },
    "OVERLAY_DECAL": {
        "effect": "Effects/terrain-overlay",
        "xsize": 1000.0,
        "ysize": 1000.0,
        "wrapu": False,
        "wrapv": False,
        "override_solid": False,
        "solid": True,
        "override_physics": False,
        "friction_factor": 0.8,
        "rolling_friction": 0.05,
        "bumpiness": 0.05,
        "load_resistance": 100000.0,
    },
}


def _normalize_key(value):
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _material_candidates(material_name):
    normalized = _normalize_key(material_name)
    candidates = [normalized]

    if normalized in TEXTURE_ALIASES:
        candidates.extend(_normalize_key(name) for name in TEXTURE_ALIASES[normalized])

    token = []
    for ch in material_name:
        if ch.isupper() and token:
            piece = _normalize_key("".join(token))
            if len(piece) > 2:
                candidates.append(piece)
            token = [ch]
        elif ch.isalnum():
            token.append(ch)
        elif token:
            piece = _normalize_key("".join(token))
            if len(piece) > 2:
                candidates.append(piece)
            token = []
    if token:
        piece = _normalize_key("".join(token))
        if len(piece) > 2:
            candidates.append(piece)

    if normalized.startswith("pa"):
        candidates.extend(["airport", "asphalt"])

    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def _is_primary_texture(filename):
    lowered = filename.lower()
    blocked = ("mask", "overlay", "relief", "colors", "structure")
    return lowered.endswith((".png", ".jpg", ".jpeg", ".dds", ".tga", ".bmp")) and not any(tag in lowered for tag in blocked)


def _texture_search_roots(texture_root):
    if not texture_root:
        return []

    roots = []
    root_path = os.path.abspath(texture_root)
    if os.path.isdir(root_path):
        roots.append(root_path)

    parent = os.path.dirname(root_path)
    for sibling in ("Terrain", "Runway"):
        sibling_path = os.path.join(parent, sibling)
        if os.path.isdir(sibling_path) and sibling_path not in roots:
            roots.append(sibling_path)

    return roots


def _texture_index(texture_root):
    search_roots = tuple(_texture_search_roots(texture_root))
    cached = _TEXTURE_INDEX_CACHE.get(search_roots)
    if cached is not None:
        return cached

    index = {}
    for root_path in search_roots:
        for walk_root, _dirs, files in os.walk(root_path):
            for filename in files:
                if not _is_primary_texture(filename):
                    continue
                full_path = os.path.join(walk_root, filename)
                stem = os.path.splitext(filename)[0]
                index.setdefault(_normalize_key(stem), []).append(full_path)

    _TEXTURE_INDEX_CACHE[search_roots] = index
    return index


def _default_material_map_path():
    return os.path.join(os.path.dirname(__file__), "material_map.json")


def _resolve_override_target(path_value, texture_root):
    if not path_value:
        return None

    if os.path.isabs(path_value) and os.path.isfile(path_value):
        return path_value

    candidates = []
    if texture_root:
        texture_root_abs = os.path.abspath(texture_root)
        candidates.append(os.path.join(texture_root_abs, path_value))
        candidates.append(os.path.join(os.path.dirname(texture_root_abs), path_value))
    candidates.append(os.path.join(os.path.dirname(__file__), path_value))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def _load_material_overrides(material_map_path):
    resolved_path = material_map_path or _default_material_map_path()
    resolved_path = os.path.abspath(resolved_path)
    cached = _MATERIAL_OVERRIDE_CACHE.get(resolved_path)
    if cached is not None:
        return cached

    data = {}
    if os.path.isfile(resolved_path):
        with open(resolved_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            data = {str(key): str(value) for key, value in loaded.items()}

    _MATERIAL_OVERRIDE_CACHE[resolved_path] = data
    return data


def _resolve_texture_path(material_name, texture_root, material_map_path=""):
    if not texture_root:
        return None

    overrides = _load_material_overrides(material_map_path)
    override_target = overrides.get(material_name) or overrides.get(_normalize_key(material_name))
    if override_target:
        resolved = _resolve_override_target(override_target, texture_root)
        if resolved:
            return resolved

    index = _texture_index(texture_root)
    for candidate in _material_candidates(material_name):
        matches = index.get(candidate)
        if matches:
            return sorted(matches)[0]

    for candidate in _material_candidates(material_name):
        partial_matches = []
        for key, paths in index.items():
            if candidate in key or key in candidate:
                partial_matches.extend(paths)
        if partial_matches:
            return sorted(partial_matches)[0]

    return None


def _fallback_color(material_name):
    for candidate in _material_candidates(material_name):
        if candidate in FALLBACK_COLORS:
            return FALLBACK_COLORS[candidate]
    return (0.5, 0.5, 0.5)


def _mtl_safe_name(name):
    safe = name.replace(" ", "_")
    return safe or "Default"


def _write_mtl(filepath, material_names, texture_root, material_map_path=""):
    material_map = {}
    with open(filepath, "w", encoding="utf-8") as mtl_file:
        mtl_file.write("# Auto-generated from FlightGear BTG\n")
        for material_name in material_names:
            safe_name = _mtl_safe_name(material_name)
            material_map[material_name] = safe_name
            mtl_file.write(f"newmtl {safe_name}\n")
            color = _fallback_color(material_name)
            mtl_file.write(f"Kd {color[0]:.6f} {color[1]:.6f} {color[2]:.6f}\n")
            mtl_file.write("Ka 0.000000 0.000000 0.000000\n")
            mtl_file.write("Ks 0.000000 0.000000 0.000000\n")
            mtl_file.write("illum 1\n")
            texture_path = _resolve_texture_path(material_name, texture_root, material_map_path)
            if texture_path:
                mtl_file.write(f"map_Kd {texture_path}\n")
            mtl_file.write("\n")
    return material_map


def _original_material_lookup(material_names):
    lookup = {}
    for material_name in material_names:
        lookup[_mtl_safe_name(material_name)] = material_name
    return lookup


def _load_blender_image(texture_path):
    if bpy is None or not texture_path:
        return None
    try:
        return bpy.data.images.load(texture_path, check_existing=True)
    except RuntimeError:
        return None


def _is_dds_texture_path(texture_path):
    return bool(texture_path) and os.path.splitext(texture_path)[1].lower() == ".dds"


def _paths_refer_to_same_file(path_a, path_b):
    if not path_a or not path_b:
        return False

    try:
        return os.path.samefile(path_a, path_b)
    except OSError:
        return os.path.abspath(path_a) == os.path.abspath(path_b)


def _material_custom_texture_override(material, texture_root, material_map_path):
    if material is None:
        return False, "", ""

    fg_material_name = str(material.get("fg_btg_material_name", "") or "").strip()
    image_path = _first_image_texture_path(material)
    if not fg_material_name or not image_path:
        return False, image_path, fg_material_name

    typed_settings = _flightgear_material_settings(material)
    has_explicit_fg_override = bool(typed_settings is not None and getattr(typed_settings, "enabled", False))
    if _is_flightgear_imported_material(material) and not has_explicit_fg_override:
        return False, image_path, fg_material_name

    resolved_default = _resolve_texture_path(fg_material_name, texture_root, material_map_path)
    if resolved_default and _paths_refer_to_same_file(image_path, resolved_default):
        return False, image_path, fg_material_name

    return True, image_path, fg_material_name


def _material_export_name(material, texture_root, material_map_path):
    if material is None:
        return "Default"

    explicit_name = str(material.get("fg_btg_material_name", "") or "").strip()
    blender_name = str(getattr(material, "name", "") or "").strip()
    has_custom_override, image_path, _fg_name = _material_custom_texture_override(
        material,
        texture_root,
        material_map_path,
    )

    if has_custom_override:
        if blender_name and _normalize_key(blender_name) != _normalize_key(explicit_name):
            return blender_name
        if image_path:
            image_stem = os.path.splitext(os.path.basename(image_path))[0].strip()
            if image_stem:
                return image_stem

    if explicit_name:
        return explicit_name
    if blender_name:
        return blender_name
    return "Default"


def _build_blender_material(material_name, texture_root, material_map_path, textured=True, force_rebuild=False):
    display_name = material_name or "Default"
    existing = bpy.data.materials.get(display_name)
    if existing is not None and not force_rebuild:
        return existing

    material = existing if existing is not None else bpy.data.materials.new(name=display_name)
    material["fg_btg_material_name"] = display_name
    material["fg_btg_imported_material"] = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (300, 0)
    shader = nodes.new(type="ShaderNodeBsdfPrincipled")
    shader.location = (0, 0)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    color = _fallback_color(display_name)
    shader.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    shader.inputs["Specular IOR Level"].default_value = 0.0

    texture_path = _resolve_texture_path(display_name, texture_root, material_map_path) if textured else None
    material["fg_btg_texture_is_dds"] = _is_dds_texture_path(texture_path)
    if texture_path:
        image = _load_blender_image(texture_path)
        if image is not None:
            tex_node = nodes.new(type="ShaderNodeTexImage")
            tex_node.location = (-300, 0)
            tex_node.image = image
            links.new(tex_node.outputs["Color"], shader.inputs["Base Color"])

    material.diffuse_color = (color[0], color[1], color[2], 1.0)
    return material


def _is_flightgear_imported_material(material):
    if material is None:
        return False
    if bool(material.get("fg_btg_imported_material", False)):
        return True
    return bool(material.get("fg_btg_material_name", ""))


def _flightgear_material_settings(material):
    if material is None:
        return None
    settings = getattr(material, "fg_btg", None)
    if settings is None:
        return None
    return settings


def _flightgear_material_image_label(material):
    image_path = _first_image_texture_path(material)
    if not image_path:
        return "No image texture"
    return os.path.basename(image_path)


def _apply_flightgear_material_preset(settings, preset_name):
    defaults = FG_MATERIAL_PRESET_DEFAULTS.get(preset_name)
    if settings is None or defaults is None:
        return False

    settings.enabled = True
    settings.effect = defaults["effect"]
    settings.xsize = defaults["xsize"]
    settings.ysize = defaults["ysize"]
    settings.wrapu = defaults["wrapu"]
    settings.wrapv = defaults["wrapv"]
    settings.override_solid = defaults["override_solid"]
    settings.solid = defaults["solid"]
    settings.override_physics = defaults["override_physics"]
    settings.friction_factor = defaults["friction_factor"]
    settings.rolling_friction = defaults["rolling_friction"]
    settings.bumpiness = defaults["bumpiness"]
    settings.load_resistance = defaults["load_resistance"]
    return True


def _flightgear_material_sync_status(material):
    if material is None:
        return "No material"
    if not _first_image_texture_path(material):
        return "No - missing image texture"
    if _is_flightgear_imported_material(material):
        has_override = bool(_flightgear_material_settings(material) and material.fg_btg.enabled)
        return "Custom override" if has_override else "Imported FG material"
    return "Yes"


def _create_material_table(face_materials, texture_root, material_map_path, textured=True):
    ordered_names = []
    seen = set()
    for material_name in face_materials:
        normalized_name = material_name or "Default"
        if normalized_name not in seen:
            seen.add(normalized_name)
            ordered_names.append(normalized_name)

    slot_lookup = {}
    material_table = {}
    for material_name in ordered_names:
        material = _build_blender_material(material_name, texture_root, material_map_path, textured=textured)
        slot_lookup[material_name] = len(material_table)
        material_table[material_name] = material

    return ordered_names, slot_lookup, material_table


def _addon_preferences(context):
    if bpy is None or context is None:
        return None
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def _resolved_string_property(value, default=""):
    return value if isinstance(value, str) else default


def _texture_root_from_context(context, override=""):
    if override:
        return override
    preferences = _addon_preferences(context)
    if preferences and getattr(preferences, "texture_root", ""):
        return preferences.texture_root
    return DEFAULT_TEXTURE_ROOT


def _infer_fg_root(texture_root):
    if not texture_root:
        return ""

    candidate = os.path.abspath(texture_root)
    while candidate and candidate != os.path.dirname(candidate):
        if os.path.basename(candidate) == "Textures":
            return os.path.dirname(candidate)
        candidate = os.path.dirname(candidate)
    return ""


def _default_materials_xml_path(texture_root):
    fg_root = _infer_fg_root(texture_root)
    if not fg_root:
        return ""

    defaults_path = os.path.join(fg_root, "defaults.xml")
    if os.path.isfile(defaults_path):
        try:
            with open(defaults_path, "r", encoding="utf-8") as handle:
                defaults_text = handle.read()
            match = re.search(
                r"<materials-file>\s*([^<]+?)\s*</materials-file>",
                defaults_text,
                flags=re.IGNORECASE,
            )
            if match:
                configured_path = match.group(1).strip().replace("\\", "/")
                configured_parts = [piece for piece in configured_path.split("/") if piece and piece not in (".", "..")]
                if configured_parts:
                    candidate = os.path.join(fg_root, *configured_parts)
                    if os.path.isfile(candidate):
                        return candidate
        except Exception:
            pass

    return os.path.join(fg_root, "Materials", "regions", "materials.xml")


def _materials_xml_library_cache_key(materials_xml_path):
    abs_path = os.path.abspath(materials_xml_path)
    try:
        stat_info = os.stat(abs_path)
        return abs_path, stat_info.st_mtime_ns, stat_info.st_size
    except OSError:
        return abs_path, 0, 0


def _parse_materials_xml_library_entries(materials_xml_path):
    with open(materials_xml_path, "r", encoding="utf-8") as handle:
        xml_text = handle.read()

    entries = []
    seen = set()
    for _start, _end, name, _block_text in _material_blocks(xml_text):
        normalized_name = (name or "").strip()
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        entries.append(normalized_name)
    return entries


def _materials_root_from_path(path_value):
    if not path_value:
        return ""

    abs_path = os.path.abspath(path_value)
    if os.path.isdir(abs_path):
        if os.path.basename(abs_path) == "Materials":
            return abs_path
        candidate = os.path.join(abs_path, "Materials")
        if os.path.isdir(candidate):
            return candidate
        return abs_path

    marker = f"{os.sep}Materials{os.sep}"
    lowered = abs_path.lower()
    marker_index = lowered.find(marker.lower())
    if marker_index >= 0:
        return abs_path[: marker_index + len("Materials") + 1]

    return os.path.dirname(abs_path)


def _materials_xml_files_under_root(materials_root):
    if not materials_root or not os.path.isdir(materials_root):
        return []

    xml_files = []
    for walk_root, _dirs, files in os.walk(materials_root):
        for filename in files:
            if filename.lower().endswith(".xml"):
                xml_files.append(os.path.join(walk_root, filename))
    return sorted(xml_files)


def _materials_root_library_cache_key(materials_root):
    abs_root = os.path.abspath(materials_root)
    signatures = []
    for xml_path in _materials_xml_files_under_root(abs_root):
        try:
            stat_info = os.stat(xml_path)
            signatures.append((xml_path, stat_info.st_mtime_ns, stat_info.st_size))
        except OSError:
            continue
    return abs_root, tuple(signatures)


def _materials_library_entries_from_materials_root(materials_root, use_cache=True):
    if not materials_root or not os.path.isdir(materials_root):
        return []

    cache_key = _materials_root_library_cache_key(materials_root)
    if use_cache:
        cached = _MATERIALS_ROOT_LIBRARY_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)

    entries = []
    seen = set()
    for xml_path in _materials_xml_files_under_root(materials_root):
        try:
            file_entries = _parse_materials_xml_library_entries(xml_path)
        except Exception:
            continue
        for material_name in file_entries:
            if material_name in seen:
                continue
            seen.add(material_name)
            entries.append(material_name)

    abs_root = cache_key[0]
    stale_keys = [key for key in _MATERIALS_ROOT_LIBRARY_CACHE if key[0] == abs_root and key != cache_key]
    for stale_key in stale_keys:
        del _MATERIALS_ROOT_LIBRARY_CACHE[stale_key]
    _MATERIALS_ROOT_LIBRARY_CACHE[cache_key] = tuple(entries)
    return entries


def _materials_xml_library_entries(materials_xml_path, use_cache=True):
    if not materials_xml_path:
        return []

    cache_key = _materials_xml_library_cache_key(materials_xml_path)
    if use_cache:
        cached = _MATERIALS_XML_LIBRARY_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)

    entries = _parse_materials_xml_library_entries(materials_xml_path)

    abs_path = cache_key[0]
    stale_keys = [key for key in _MATERIALS_XML_LIBRARY_CACHE if key[0] == abs_path and key != cache_key]
    for stale_key in stale_keys:
        del _MATERIALS_XML_LIBRARY_CACHE[stale_key]
    _MATERIALS_XML_LIBRARY_CACHE[cache_key] = tuple(entries)
    return entries


def _resolved_materials_xml_path(context, materials_xml_override=""):
    override_path = _resolved_string_property(materials_xml_override, "").strip()
    if override_path:
        return os.path.abspath(override_path)

    texture_root = _texture_root_from_context(context)
    return _default_materials_xml_path(texture_root)


def _resolved_materials_root(context, materials_xml_override=""):
    override_path = _resolved_string_property(materials_xml_override, "").strip()
    if override_path:
        return _materials_root_from_path(override_path)

    texture_root = _texture_root_from_context(context)
    fg_root = _infer_fg_root(texture_root)
    if not fg_root:
        return ""
    return os.path.join(fg_root, "Materials")


def _material_library_entries(context, materials_xml_override="", use_cache=True, recursive_fallback=True):
    materials_xml_path = _resolved_materials_xml_path(context, materials_xml_override)
    entries = []
    seen = set()

    if materials_xml_path and os.path.isfile(materials_xml_path):
        for material_name in _materials_xml_library_entries(materials_xml_path, use_cache=use_cache):
            if material_name in seen:
                continue
            seen.add(material_name)
            entries.append(material_name)

    if not recursive_fallback:
        return entries

    materials_root = _resolved_materials_root(context, materials_xml_override)
    if not materials_root:
        return entries

    for material_name in _materials_library_entries_from_materials_root(materials_root, use_cache=use_cache):
        if material_name in seen:
            continue
        seen.add(material_name)
        entries.append(material_name)

    return entries


def _fg_material_library_enum_items(_self, context):
    if bpy is None:
        return []

    try:
        entries = _material_library_entries(context, use_cache=True, recursive_fallback=True)
        return [(name, name, f"FlightGear material '{name}'") for name in entries]
    except Exception:
        return []


def _material_real_user_count(material):
    if material is None:
        return 0
    users = int(getattr(material, "users", 0) or 0)
    if bool(getattr(material, "use_fake_user", False)):
        return max(0, users - 1)
    return users


def _first_image_texture_path(material):
    if material is None or not getattr(material, "use_nodes", False):
        return ""
    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return ""

    for node in node_tree.nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        if image is None:
            continue
        image_path = ""
        if hasattr(image, "filepath_from_user"):
            image_path = image.filepath_from_user()
        elif hasattr(image, "filepath"):
            image_path = image.filepath
        if not image_path:
            continue
        if bpy is not None:
            image_path = bpy.path.abspath(image_path)
        image_path = os.path.abspath(image_path)
        if os.path.isfile(image_path):
            return image_path

    return ""


def _material_uses_dds(material):
    if material is None:
        return False

    explicit = material.get("fg_btg_texture_is_dds") if hasattr(material, "get") else None
    if isinstance(explicit, bool):
        return explicit

    image_path = _first_image_texture_path(material)
    return _is_dds_texture_path(image_path)


def _material_wrap_flags(material, material_name, wrap_settings_map=None):
    typed_settings = _flightgear_material_settings(material)
    if typed_settings is not None and bool(getattr(typed_settings, "enabled", False)):
        return (
            bool(getattr(typed_settings, "wrapu", True)),
            bool(getattr(typed_settings, "wrapv", True)),
        )

    if material is not None and hasattr(material, "get"):
        explicit_wrapu = material.get("fg_btg_wrapu")
        explicit_wrapv = material.get("fg_btg_wrapv")
        if isinstance(explicit_wrapu, bool) or isinstance(explicit_wrapv, bool):
            return (
                True if explicit_wrapu is None else bool(explicit_wrapu),
                True if explicit_wrapv is None else bool(explicit_wrapv),
            )

    if wrap_settings_map:
        settings = wrap_settings_map.get(_normalize_key(material_name or ""))
        if settings is not None:
            wrapu = settings.get("wrapu")
            wrapv = settings.get("wrapv")
            return (
                True if wrapu is None else bool(wrapu),
                True if wrapv is None else bool(wrapv),
            )

    return True, True


def _copy_material_texture(image_path, fg_root, texture_subdir, overwrite_existing=False):
    if not image_path or not fg_root:
        return "", ""

    textures_root = os.path.join(fg_root, "Textures")
    subdir = (texture_subdir or "bfg-exporter").strip().replace("\\", "/")
    subdir = "/".join(piece for piece in subdir.split("/") if piece not in ("", ".", ".."))
    if not subdir:
        subdir = "bfg-exporter"

    target_dir = os.path.join(textures_root, subdir)
    os.makedirs(target_dir, exist_ok=True)

    base_name = os.path.basename(image_path)
    stem, ext = os.path.splitext(base_name)
    ext = ext.lower()
    if not ext:
        ext = ".png"
    if not stem:
        stem = "texture"

    dest_name = f"{stem}{ext}"
    dest_path = os.path.join(target_dir, dest_name)
    rel = "/".join((subdir, dest_name))

    if os.path.exists(dest_path):
        try:
            if os.path.samefile(image_path, dest_path):
                return rel, dest_path
        except OSError:
            pass

        src_stat = os.stat(image_path)
        dst_stat = os.stat(dest_path)
        src_is_newer = src_stat.st_mtime > dst_stat.st_mtime
        size_differs = src_stat.st_size != dst_stat.st_size

        if not src_is_newer and not size_differs:
            return rel, dest_path

        if not (overwrite_existing or src_is_newer or size_differs):
            return rel, dest_path

    shutil.copy2(image_path, dest_path)
    return rel, dest_path


def _material_name_from_block(material_block_text):
    match = re.search(r"<name>\s*([^<]+?)\s*</name>", material_block_text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _material_blocks(xml_text):
    pattern = re.compile(r"<material\b[^>]*>.*?</material>", flags=re.IGNORECASE | re.DOTALL)
    blocks = []
    for match in pattern.finditer(xml_text):
        block_text = match.group(0)
        name = _material_name_from_block(block_text)
        blocks.append((match.start(), match.end(), name, block_text))
    return blocks


def _material_block_bool_value(material_block_text, field_name):
    match = re.search(
        rf"<{re.escape(field_name)}>\s*([^<]+?)\s*</{re.escape(field_name)}>",
        material_block_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    value = match.group(1).strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return None


def _material_wrap_settings_map(context, materials_xml_override=""):
    wrap_settings = {}

    def merge_xml_path(xml_path):
        if not xml_path or not os.path.isfile(xml_path):
            return
        try:
            with open(xml_path, "r", encoding="utf-8") as handle:
                xml_text = handle.read()
        except OSError:
            return

        for _start, _end, material_name, block_text in _material_blocks(xml_text):
            normalized_name = _normalize_key(material_name or "")
            if not normalized_name or normalized_name in wrap_settings:
                continue
            wrap_settings[normalized_name] = {
                "wrapu": _material_block_bool_value(block_text, "wrapu"),
                "wrapv": _material_block_bool_value(block_text, "wrapv"),
            }

    materials_xml_path = _resolved_materials_xml_path(context, materials_xml_override)
    merge_xml_path(materials_xml_path)

    materials_root = _resolved_materials_root(context, materials_xml_override)
    if materials_root:
        for xml_path in _materials_xml_files_under_root(materials_root):
            merge_xml_path(xml_path)

    return wrap_settings


def _extract_managed_block(xml_text):
    start = xml_text.find(_MANAGED_MATERIALS_BEGIN)
    if start < 0:
        return None
    end_marker = xml_text.find(_MANAGED_MATERIALS_END, start)
    if end_marker < 0:
        return None
    end = end_marker + len(_MANAGED_MATERIALS_END)
    return start, end, xml_text[start:end]


def _strip_managed_block(xml_text):
    block = _extract_managed_block(xml_text)
    if not block:
        return xml_text, ""
    start, end, text = block
    tail = end
    if tail < len(xml_text) and xml_text[tail:tail + 1] == "\n":
        tail += 1
    return xml_text[:start] + xml_text[tail:], text


def _remove_named_material_blocks(xml_text, names):
    if not names:
        return xml_text
    names_set = set(names)
    out = []
    cursor = 0
    for start, end, name, _block_text in _material_blocks(xml_text):
        if name in names_set:
            out.append(xml_text[cursor:start])
            cursor = end
    out.append(xml_text[cursor:])
    return "".join(out)


def _material_xml_settings_from_blender_material(material, texture_rel_path):
    settings = {
        "effect": "Effects/terrain-default",
        "texture": texture_rel_path,
        "xsize": 1000,
        "ysize": 1000,
        "wrapu": None,
        "wrapv": None,
        "solid": None,
        "friction-factor": None,
        "rolling-friction": None,
        "bumpiness": None,
        "load-resistance": None,
    }

    if material is None:
        return settings

    typed_settings = _flightgear_material_settings(material)
    if typed_settings is not None and bool(getattr(typed_settings, "enabled", False)):
        effect_value = str(getattr(typed_settings, "effect", "") or "").strip()
        if effect_value:
            settings["effect"] = effect_value
        settings["xsize"] = float(getattr(typed_settings, "xsize", settings["xsize"]))
        settings["ysize"] = float(getattr(typed_settings, "ysize", settings["ysize"]))
        settings["wrapu"] = bool(getattr(typed_settings, "wrapu", True))
        settings["wrapv"] = bool(getattr(typed_settings, "wrapv", True))

        if bool(getattr(typed_settings, "override_solid", False)):
            settings["solid"] = bool(getattr(typed_settings, "solid", True))

        if bool(getattr(typed_settings, "override_physics", False)):
            settings["friction-factor"] = float(getattr(typed_settings, "friction_factor", 0.8))
            settings["rolling-friction"] = float(getattr(typed_settings, "rolling_friction", 0.05))
            settings["bumpiness"] = float(getattr(typed_settings, "bumpiness", 0.05))
            settings["load-resistance"] = float(getattr(typed_settings, "load_resistance", 100000.0))

        return settings

    effect_value = str(material.get("fg_btg_effect", "") or "").strip()
    if effect_value:
        settings["effect"] = effect_value

    numeric_fields = {
        "xsize": "fg_btg_xsize",
        "ysize": "fg_btg_ysize",
        "friction-factor": "fg_btg_friction_factor",
        "rolling-friction": "fg_btg_rolling_friction",
        "bumpiness": "fg_btg_bumpiness",
        "load-resistance": "fg_btg_load_resistance",
    }
    for xml_name, prop_name in numeric_fields.items():
        value = material.get(prop_name)
        if isinstance(value, (int, float)):
            settings[xml_name] = value

    bool_fields = {
        "wrapu": "fg_btg_wrapu",
        "wrapv": "fg_btg_wrapv",
        "solid": "fg_btg_solid",
    }
    for xml_name, prop_name in bool_fields.items():
        value = material.get(prop_name)
        if isinstance(value, bool):
            settings[xml_name] = value
        elif isinstance(value, (int, float)):
            settings[xml_name] = bool(value)

    return settings


def _format_material_xml_scalar(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _build_material_xml_entry(material_name, entry_settings):
    if isinstance(entry_settings, str):
        entry_settings = _material_xml_settings_from_blender_material(None, entry_settings)

    safe_name = _xml_escape(material_name)
    safe_tex = _xml_escape(str(entry_settings.get("texture", "") or ""))
    safe_effect = _xml_escape(str(entry_settings.get("effect", "Effects/terrain-default") or "Effects/terrain-default"))
    lines = [
        "  <material>",
        f"    <name>{safe_name}</name>",
        f"    <effect>{safe_effect}</effect>",
        f"    <texture>{safe_tex}</texture>",
        f"    <xsize>{_format_material_xml_scalar(entry_settings.get('xsize', 1000))}</xsize>",
        f"    <ysize>{_format_material_xml_scalar(entry_settings.get('ysize', 1000))}</ysize>",
    ]

    optional_fields = (
        "wrapu",
        "wrapv",
        "solid",
        "friction-factor",
        "rolling-friction",
        "bumpiness",
        "load-resistance",
    )
    for field_name in optional_fields:
        value = entry_settings.get(field_name)
        if value is None:
            continue
        lines.append(f"    <{field_name}>{_format_material_xml_scalar(value)}</{field_name}>")

    lines.append("  </material>")
    return "\n".join(lines)


def _build_managed_materials_block(entries):
    lines = [
        _MANAGED_MATERIALS_BEGIN,
        "<region name=\"bfg-exporter\">",
    ]
    for material_name, entry_settings in entries.items():
        lines.append(_build_material_xml_entry(material_name, entry_settings))
    lines.extend([
        "</region>",
        _MANAGED_MATERIALS_END,
    ])
    return "\n".join(lines)


def _format_material_sync_pairs(mapping, limit=8):
    if not mapping:
        return ""

    items = sorted(mapping.items())
    shown = items[: max(1, int(limit))]
    rendered = ", ".join(f"{name} -> {texture_rel}" for name, texture_rel in shown)
    if len(items) > len(shown):
        rendered += f", ... (+{len(items) - len(shown)} more)"
    return rendered


def _upsert_exporter_materials_xml(
    materials_xml_path,
    new_material_entries,
    overwrite_existing=False,
):
    if not materials_xml_path:
        raise ValueError("No materials.xml path provided")

    parent_dir = os.path.dirname(materials_xml_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    if os.path.isfile(materials_xml_path):
        with open(materials_xml_path, "r", encoding="utf-8") as handle:
            xml_text = handle.read()
    else:
        xml_text = "<?xml version=\"1.0\"?>\n<PropertyList>\n</PropertyList>\n"

    outside_text, managed_block_text = _strip_managed_block(xml_text)

    managed_entries = {}
    for _start, _end, name, block_text in _material_blocks(managed_block_text):
        if not name:
            continue
        tex_match = re.search(r"<texture>\s*([^<]+?)\s*</texture>", block_text, flags=re.IGNORECASE)
        tex_rel = tex_match.group(1).strip() if tex_match else ""
        effect_match = re.search(r"<effect>\s*([^<]+?)\s*</effect>", block_text, flags=re.IGNORECASE)
        effect_value = effect_match.group(1).strip() if effect_match else "Effects/terrain-default"
        xsize_match = re.search(r"<xsize>\s*([^<]+?)\s*</xsize>", block_text, flags=re.IGNORECASE)
        ysize_match = re.search(r"<ysize>\s*([^<]+?)\s*</ysize>", block_text, flags=re.IGNORECASE)
        managed_entries[name] = {
            "effect": effect_value,
            "texture": tex_rel,
            "xsize": xsize_match.group(1).strip() if xsize_match else "1000",
            "ysize": ysize_match.group(1).strip() if ysize_match else "1000",
        }

    outside_names = {name for _start, _end, name, _block in _material_blocks(outside_text) if name}

    inserted = []
    updated = []
    skipped_existing = []
    overwrite_remove_names = []

    for material_name, entry_settings in new_material_entries.items():
        in_managed = material_name in managed_entries
        in_outside = material_name in outside_names

        if (in_managed or in_outside) and not overwrite_existing:
            skipped_existing.append(material_name)
            continue

        if in_outside and overwrite_existing:
            overwrite_remove_names.append(material_name)

        if in_managed:
            updated.append(material_name)
        else:
            inserted.append(material_name)

        managed_entries[material_name] = entry_settings

    if overwrite_remove_names:
        outside_text = _remove_named_material_blocks(outside_text, overwrite_remove_names)

    if managed_entries:
        managed_block = _build_managed_materials_block(managed_entries)
        closing_idx = outside_text.rfind("</PropertyList>")
        if closing_idx >= 0:
            head = outside_text[:closing_idx].rstrip()
            tail = outside_text[closing_idx:]
            xml_text = f"{head}\n\n{managed_block}\n{tail}"
        else:
            xml_text = outside_text.rstrip() + "\n\n" + managed_block + "\n"
    else:
        xml_text = outside_text

    with open(materials_xml_path, "w", encoding="utf-8") as handle:
        handle.write(xml_text)

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped_existing": skipped_existing,
    }


def _material_usage_from_mesh_objects(
    mesh_objects,
    exported_material_names,
    texture_root,
    material_map_path,
):
    names = set(exported_material_names)
    usage = {}
    for obj in mesh_objects:
        materials = getattr(getattr(obj, "data", None), "materials", None)
        if not materials:
            continue
        for material in materials:
            if material is None:
                continue
            fg_name = _material_export_name(material, texture_root, material_map_path)
            if fg_name in names and fg_name not in usage:
                usage[fg_name] = material
    return usage
