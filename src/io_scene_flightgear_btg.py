bl_info = {
    "name": "FlightGear BTG Import/Export",
    "author": "Federico Contreras",
    "version": (0, 0, 7),
    "blender": (4, 0, 0),
    "location": "File > Import-Export",
    "description": "Import and export FlightGear TerraGear BTG scenery geometry files",
    "category": "Import-Export",
}

import gzip
import json
import math
import os
import re
import shutil
import struct
import time
from xml.sax.saxutils import escape as _xml_escape

try:
    import bmesh  # type: ignore[import-not-found]
    import bpy  # type: ignore[import-not-found]
    from mathutils import Matrix, Vector  # type: ignore[import-not-found]
    from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty  # type: ignore[import-not-found]
    from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup  # type: ignore[import-not-found]
    from bpy_extras.io_utils import ExportHelper, ImportHelper  # type: ignore[import-not-found]
except ModuleNotFoundError:
    # Allow parser/export helper functions to be imported for non-Blender tests.
    bmesh = None
    bpy = None
    Matrix = None
    Vector = None

    def BoolProperty(**_kwargs):
        return None

    def StringProperty(**_kwargs):
        return None

    def EnumProperty(**_kwargs):
        return None

    def FloatProperty(**_kwargs):
        return None

    def IntProperty(**_kwargs):
        return None

    def PointerProperty(**_kwargs):
        return None

    class AddonPreferences:
        pass

    class Operator:
        pass

    class Panel:
        pass

    class PropertyGroup:
        pass

    class ImportHelper:
        pass

    class ExportHelper:
        pass


try:
    from .fg_btg_btgio import BTGData, _decompress_btg_gz_to_folder, parse_btg, write_btg
    from .fg_btg_geo import (
        _adjacent_btg_paths,
        _bucket_base_path,
        _bucket_center_lon_lat,
        _bucket_corner_lon_lat,
        _bucket_from_index,
        _ecef_to_enu_matrix,
        _geodetic_to_ecef,
        _normalize3,
        _point_group_tile_index_from_name,
        _rotate3,
        _rotate3_inv,
        _scene_vertices_from_btg,
        _tile_index_from_path,
    )
    from .fg_btg_materials import (
        _apply_flightgear_material_preset,
        _build_blender_material,
        _copy_material_texture,
        _create_material_table,
        _default_material_map_path,
        _default_materials_xml_path,
        _fg_material_library_enum_items,
        _first_image_texture_path,
        _flightgear_material_image_label,
        _flightgear_material_settings,
        _flightgear_material_sync_status,
        _format_material_sync_pairs,
        _infer_fg_root,
        _is_dds_texture_path,
        _is_flightgear_imported_material,
        _material_custom_texture_override,
        _material_export_name,
        _material_library_entries,
        _material_real_user_count,
        _material_xml_settings_from_blender_material,
        _material_usage_from_mesh_objects,
        _material_uses_dds,
        _material_wrap_flags,
        _material_wrap_settings_map,
        _mtl_safe_name,
        _resolve_texture_path,
        _resolved_materials_root,
        _upsert_exporter_materials_xml,
        _write_mtl,
    )
    from .fg_btg_scene import (
        _btg_output_basename,
        _center_from_objects,
        _extract_export_mesh_data,
        _has_adjacent_reference_tiles,
        _has_mixed_btg_centers,
        _has_untagged_meshes_for_btg_export,
        _is_point_group_object,
        _max_radius_from_center,
        _package_btg_destination_preview,
        _point_group_vertex_count,
        _source_basename_for_objects,
        _stg_path_for_btg_export,
        _suspicious_base_tile_replacement_message,
        _upsert_stg_object_base,
    )
    from .fg_btg_ui_registry import (
        apply_class_properties,
        build_classes,
        make_menu_functions,
        register_addon,
        unregister_addon,
    )
except ImportError:
    from fg_btg_btgio import BTGData, _decompress_btg_gz_to_folder, parse_btg, write_btg
    from fg_btg_geo import (
        _adjacent_btg_paths,
        _bucket_base_path,
        _bucket_center_lon_lat,
        _bucket_corner_lon_lat,
        _bucket_from_index,
        _ecef_to_enu_matrix,
        _geodetic_to_ecef,
        _normalize3,
        _point_group_tile_index_from_name,
        _rotate3,
        _rotate3_inv,
        _scene_vertices_from_btg,
        _tile_index_from_path,
    )
    from fg_btg_materials import (
        _apply_flightgear_material_preset,
        _build_blender_material,
        _copy_material_texture,
        _create_material_table,
        _default_material_map_path,
        _default_materials_xml_path,
        _fg_material_library_enum_items,
        _first_image_texture_path,
        _flightgear_material_image_label,
        _flightgear_material_settings,
        _flightgear_material_sync_status,
        _format_material_sync_pairs,
        _infer_fg_root,
        _is_dds_texture_path,
        _is_flightgear_imported_material,
        _material_custom_texture_override,
        _material_export_name,
        _material_library_entries,
        _material_real_user_count,
        _material_xml_settings_from_blender_material,
        _material_usage_from_mesh_objects,
        _material_uses_dds,
        _material_wrap_flags,
        _material_wrap_settings_map,
        _mtl_safe_name,
        _resolve_texture_path,
        _resolved_materials_root,
        _upsert_exporter_materials_xml,
        _write_mtl,
    )
    from fg_btg_scene import (
        _btg_output_basename,
        _center_from_objects,
        _extract_export_mesh_data,
        _has_adjacent_reference_tiles,
        _has_mixed_btg_centers,
        _has_untagged_meshes_for_btg_export,
        _is_point_group_object,
        _max_radius_from_center,
        _package_btg_destination_preview,
        _point_group_vertex_count,
        _source_basename_for_objects,
        _stg_path_for_btg_export,
        _suspicious_base_tile_replacement_message,
        _upsert_stg_object_base,
    )
    from fg_btg_ui_registry import (
        apply_class_properties,
        build_classes,
        make_menu_functions,
        register_addon,
        unregister_addon,
    )


BTG_MAGIC = 0x5347
IMPORT_SCALE = 0.01
EXPORT_SCALE = 100.0
DEFAULT_TEXTURE_ROOT = "/usr/share/games/flightgear/Textures/"
ADDON_ID = __package__ or os.path.splitext(os.path.basename(__file__))[0]
SG_BUCKET_SPAN = 0.125
SG_HALF_BUCKET_SPAN = 0.5 * SG_BUCKET_SPAN
SG_EPSILON = 1e-7
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3




def _placeholder_btg_data_for_bucket(bucket, material_name="ocean"):
    center_lon, center_lat = _bucket_center_lon_lat(bucket)
    center = _geodetic_to_ecef(center_lon, center_lat, 0.0)
    corner_lon_lat = _bucket_corner_lon_lat(bucket)
    corner_ecef = [_geodetic_to_ecef(lon, lat, 0.0) for lon, lat in corner_lon_lat]
    vertices = [
        (x - center[0], y - center[1], z - center[2])
        for x, y, z in corner_ecef
    ]

    btg_data = BTGData()
    btg_data.center = center
    btg_data.vertices = vertices
    btg_data.faces = [(0, 1, 2), (0, 2, 3)]
    btg_data.texcoords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    btg_data.face_texcoords = [(0, 1, 2), (0, 2, 3)]
    resolved_material = material_name or "ocean"
    btg_data.face_materials = [resolved_material, resolved_material]
    btg_data.point_groups = []
    btg_data.radius = max(
        math.sqrt(vx * vx + vy * vy + vz * vz)
        for vx, vy, vz in vertices
    ) if vertices else 0.0
    return btg_data


def _create_blender_mesh_object(
    context,
    btg_path,
    btg_data,
    texture_root,
    material_map_path,
    textured_materials=True,
    flip_dds_v_for_view=True,
    target_collection=None,
    select_imported=True,
    reference_center=None,
    reference_enu_rot=None,
    reference_z_offset=None,
    is_adjacent_reference=False,
):
    if bpy is None:
        raise RuntimeError("Direct BTG import requires Blender's Python runtime")

    object_name = os.path.splitext(os.path.basename(btg_path))[0]

    # Rotate tile geometry into Blender's ENU frame.  Adjacent reference tiles
    # reuse the anchor tile's ENU frame and Z offset so they land around the
    # active tile instead of all re-centering at the origin.
    scaled_vertices_all, mean_z = _scene_vertices_from_btg(
        btg_data,
        reference_center=reference_center,
        reference_enu_rot=reference_enu_rot,
        reference_z_offset=reference_z_offset,
    )

    # Keep terrain mesh focused on renderable faces and import SG_POINTS into
    # dedicated companion objects so they are easy to identify and preserve.
    face_vertex_indices = set()
    for a, b, c in btg_data.faces:
        face_vertex_indices.add(a)
        face_vertex_indices.add(b)
        face_vertex_indices.add(c)

    if face_vertex_indices:
        sorted_face_indices = sorted(face_vertex_indices)
        remap = {old_idx: new_idx for new_idx, old_idx in enumerate(sorted_face_indices)}
        scaled_vertices = [scaled_vertices_all[old_idx] for old_idx in sorted_face_indices]
        remapped_faces = [
            (remap[a], remap[b], remap[c])
            for a, b, c in btg_data.faces
            if a in remap and b in remap and c in remap
        ]
    else:
        scaled_vertices = list(scaled_vertices_all)
        remapped_faces = []

    mesh = bpy.data.meshes.new(object_name)
    mesh.from_pydata(scaled_vertices, [], remapped_faces)
    mesh.update()

    point_material_names = [
        (group.get("material", "") or "Default")
        for group in btg_data.point_groups
    ]
    ordered_names, slot_lookup, material_table = _create_material_table(
        btg_data.face_materials + point_material_names,
        texture_root,
        material_map_path,
        textured=textured_materials,
    )

    for material_name in ordered_names:
        mesh.materials.append(material_table[material_name])

    for poly_index, polygon in enumerate(mesh.polygons):
        material_name = btg_data.face_materials[poly_index] if poly_index < len(btg_data.face_materials) else "Default"
        polygon.material_index = slot_lookup.get(material_name or "Default", 0)

    if btg_data.texcoords and btg_data.face_texcoords:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for poly_index, polygon in enumerate(mesh.polygons):
            uv_indices = btg_data.face_texcoords[poly_index] if poly_index < len(btg_data.face_texcoords) else (None, None, None)
            material = mesh.materials[polygon.material_index] if polygon.material_index < len(mesh.materials) else None
            flip_v_for_dds = bool(flip_dds_v_for_view and _material_uses_dds(material))
            for corner_index, loop_index in enumerate(polygon.loop_indices):
                uv_index = uv_indices[corner_index] if corner_index < len(uv_indices) else None
                if uv_index is not None and 0 <= uv_index < len(btg_data.texcoords):
                    u, v = btg_data.texcoords[uv_index]
                    uv_layer.data[loop_index].uv = (u, 1.0 - v) if flip_v_for_dds else (u, v)
                else:
                    uv_layer.data[loop_index].uv = (0.0, 0.0)

    obj = bpy.data.objects.new(object_name, mesh)
    target_collection = target_collection or getattr(context, "collection", None) or context.scene.collection
    target_collection.objects.link(obj)
    if select_imported:
        for selected_obj in context.selected_objects:
            selected_obj.select_set(False)
        context.view_layer.objects.active = obj
        obj.select_set(True)

    obj["fg_btg_center_x"] = btg_data.center[0]
    obj["fg_btg_center_y"] = btg_data.center[1]
    obj["fg_btg_center_z"] = btg_data.center[2]
    obj["fg_btg_source"] = btg_path
    obj["fg_btg_import_scale"] = IMPORT_SCALE
    obj["fg_btg_original_radius"] = float(btg_data.radius)
    obj["fg_btg_original_vertex_count"] = len(btg_data.vertices)
    obj["fg_btg_original_face_count"] = len(btg_data.faces)
    # Flag indicating that vertex coordinates have been rotated from ECEF to ENU.
    # The inverse rotation is applied automatically at BTG export time.
    obj["fg_btg_enu_applied"] = True
    # Z offset (in Blender units) that was subtracted from all vertices on import
    # to centre the tile near Z=0.  Added back before the inverse ENU rotation
    # on export so the round-trip is lossless.
    obj["fg_btg_z_offset"] = mean_z
    if is_adjacent_reference:
        obj["fg_btg_is_adjacent_reference"] = True

    # Import SG_POINTS as companion objects to avoid accidental deletion of
    # light point geometry embedded as loose vertices in the main tile mesh.
    if btg_data.point_groups:
        point_collection = _ensure_child_collection(context.scene.collection, "BTG Point Lights")
        tile_index = _tile_index_from_path(btg_path)
        point_name_prefix = str(tile_index) if tile_index is not None else _btg_output_basename(btg_path)
        use_single_light_name = len(btg_data.point_groups) == 1
        for group_idx, point_group in enumerate(btg_data.point_groups):
            point_indices = point_group.get("indices", [])
            unique_indices = []
            seen_indices = set()
            for idx in point_indices:
                if idx in seen_indices:
                    continue
                if 0 <= idx < len(scaled_vertices_all):
                    seen_indices.add(idx)
                    unique_indices.append(idx)
            if not unique_indices:
                continue

            point_coords = [scaled_vertices_all[idx] for idx in unique_indices]
            if use_single_light_name:
                point_mesh_name = f"{point_name_prefix}_lights"
            else:
                point_mesh_name = f"{point_name_prefix}_lights_{group_idx:03d}"
            point_mesh = bpy.data.meshes.new(point_mesh_name)
            # Connect consecutive vertices with edges so that the polyline is
            # visible as bright orange lines in Blender's Edit Mode.  Without
            # edges, only tiny vertex dots are drawn and they are occluded by
            # the terrain mesh (show_in_front does not override depth-testing
            # in Edit Mode the way it does in Object Mode).
            point_edges = [(i, i + 1) for i in range(len(point_coords) - 1)]
            point_mesh.from_pydata(point_coords, point_edges, [])
            point_mesh.update()

            material_name = point_group.get("material", "") or "Default"
            point_material = material_table.get(material_name)
            if point_material is not None:
                point_mesh.materials.append(point_material)

            point_obj = bpy.data.objects.new(point_mesh_name, point_mesh)
            point_obj.display_type = "WIRE"
            point_obj.show_name = True
            point_obj.show_in_front = True
            point_obj.parent = obj
            if point_collection is not None:
                point_collection.objects.link(point_obj)
            else:
                target_collection.objects.link(point_obj)

            point_obj["fg_btg_is_point_group"] = True
            point_obj["fg_btg_point_material"] = material_name
            point_obj["fg_btg_center_x"] = btg_data.center[0]
            point_obj["fg_btg_center_y"] = btg_data.center[1]
            point_obj["fg_btg_center_z"] = btg_data.center[2]
            point_obj["fg_btg_source"] = btg_path
            point_obj["fg_btg_import_scale"] = IMPORT_SCALE
            point_obj["fg_btg_enu_applied"] = True
            point_obj["fg_btg_z_offset"] = mean_z
            if is_adjacent_reference:
                point_obj["fg_btg_is_adjacent_reference"] = True

    return obj


def _addon_preferences(context):
    if bpy is None or context is None:
        return None
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def _texture_root_from_context(context, override=""):
    if override:
        return override
    preferences = _addon_preferences(context)
    if preferences and getattr(preferences, "texture_root", ""):
        return preferences.texture_root
    return DEFAULT_TEXTURE_ROOT


def _material_map_path_from_context(context):
    preferences = _addon_preferences(context)
    if preferences and getattr(preferences, "material_map_path", ""):
        return preferences.material_map_path
    return _default_material_map_path()


def _resolved_string_property(value, default=""):
    return value if isinstance(value, str) else default


def _resolved_bool_property(value, default=False):
    return value if isinstance(value, bool) else default


def _ensure_child_collection(parent_collection, collection_name):
    if bpy is None:
        return None

    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)

    if parent_collection is not None:
        already_linked = any(child == collection for child in parent_collection.children)
        if not already_linked:
            parent_collection.children.link(collection)

    return collection


def _adjacent_collection_name(anchor_obj):
    return f"{anchor_obj.name} Adjacent Tiles"


def _resolve_anchor_tile_object(context):
    obj = getattr(context, "active_object", None)
    if obj is None:
        return None, "No active object. Select an imported FlightGear tile first."

    if obj.get("fg_btg_is_point_group") and getattr(obj, "parent", None) is not None:
        obj = obj.parent

    if obj is None or obj.type != "MESH":
        return None, "Active object must be an imported FlightGear mesh tile."

    source_path = obj.get("fg_btg_source")
    if not isinstance(source_path, str) or not source_path:
        return None, "Active object is not an imported FlightGear tile."

    if obj.get("fg_btg_is_adjacent_reference"):
        return None, "Select the main tile, not one of its adjacent reference tiles."

    return obj, ""


def _resolve_mesh_object_for_conform(scene, object_name):
    if scene is None:
        return None

    name = str(object_name or "").strip()
    if not name:
        return None

    obj = scene.objects.get(name)
    if obj is None:
        return None

    if obj.get("fg_btg_is_point_group") and getattr(obj, "parent", None) is not None:
        obj = obj.parent

    if obj is None or obj.type != "MESH":
        return None
    return obj


def _scene_working_mesh_name(scene):
    return _resolved_string_property(getattr(scene, "fg_btg_working_mesh_name", ""), "")


def _scene_reference_mesh_name(scene):
    return _resolved_string_property(getattr(scene, "fg_btg_reference_mesh_name", ""), "")


def _set_scene_working_mesh_name(scene, value):
    if scene is not None:
        try:
            scene.fg_btg_working_mesh_name = str(value or "")
        except AttributeError:
            pass


def _set_scene_reference_mesh_name(scene, value):
    if scene is not None:
        try:
            scene.fg_btg_reference_mesh_name = str(value or "")
        except AttributeError:
            pass


def _mat3_transpose(matrix):
    return (
        (matrix[0][0], matrix[1][0], matrix[2][0]),
        (matrix[0][1], matrix[1][1], matrix[2][1]),
        (matrix[0][2], matrix[1][2], matrix[2][2]),
    )


def _mat3_mul(left, right):
    return (
        (
            left[0][0] * right[0][0] + left[0][1] * right[1][0] + left[0][2] * right[2][0],
            left[0][0] * right[0][1] + left[0][1] * right[1][1] + left[0][2] * right[2][1],
            left[0][0] * right[0][2] + left[0][1] * right[1][2] + left[0][2] * right[2][2],
        ),
        (
            left[1][0] * right[0][0] + left[1][1] * right[1][0] + left[1][2] * right[2][0],
            left[1][0] * right[0][1] + left[1][1] * right[1][1] + left[1][2] * right[2][1],
            left[1][0] * right[0][2] + left[1][1] * right[1][2] + left[1][2] * right[2][2],
        ),
        (
            left[2][0] * right[0][0] + left[2][1] * right[1][0] + left[2][2] * right[2][0],
            left[2][0] * right[0][1] + left[2][1] * right[1][1] + left[2][2] * right[2][1],
            left[2][0] * right[0][2] + left[2][1] * right[1][2] + left[2][2] * right[2][2],
        ),
    )


def _mat3_vec_mul(matrix, vector):
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )


def _object_btg_frame(obj):
    center_x = obj.get("fg_btg_center_x")
    center_y = obj.get("fg_btg_center_y")
    center_z = obj.get("fg_btg_center_z")
    if center_x is None or center_y is None or center_z is None:
        return None

    try:
        center = (float(center_x), float(center_y), float(center_z))
        import_scale = float(obj.get("fg_btg_import_scale", IMPORT_SCALE))
        z_offset = float(obj.get("fg_btg_z_offset", 0.0))
    except (TypeError, ValueError):
        return None

    if abs(import_scale) <= 1e-12:
        import_scale = IMPORT_SCALE

    return {
        "center": center,
        "import_scale": import_scale,
        "z_offset": z_offset,
        "enu_applied": bool(obj.get("fg_btg_enu_applied")),
    }


def _metadata_alignment_matrix(source_obj, anchor_obj):
    if Matrix is None:
        return None, "This operator requires Blender runtime"

    source_frame = _object_btg_frame(source_obj)
    anchor_frame = _object_btg_frame(anchor_obj)
    if source_frame is None:
        return None, f"'{source_obj.name}' is missing fg_btg_center_* metadata."
    if anchor_frame is None:
        return None, "Active anchor tile is missing fg_btg_center_* metadata."

    source_center = source_frame["center"]
    anchor_center = anchor_frame["center"]
    source_scale = source_frame["import_scale"]
    anchor_scale = anchor_frame["import_scale"]
    source_z_offset = source_frame["z_offset"]
    anchor_z_offset = anchor_frame["z_offset"]

    source_rot = _ecef_to_enu_matrix(*source_center) if source_frame["enu_applied"] else (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    anchor_rot = _ecef_to_enu_matrix(*anchor_center) if anchor_frame["enu_applied"] else (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    source_rot_inv = _mat3_transpose(source_rot)
    rotation = _mat3_mul(anchor_rot, source_rot_inv)
    scale_ratio = anchor_scale / source_scale
    rotation_scaled = tuple(
        tuple(component * scale_ratio for component in row)
        for row in rotation
    )

    center_delta_scene = (
        (source_center[0] - anchor_center[0]) * anchor_scale,
        (source_center[1] - anchor_center[1]) * anchor_scale,
        (source_center[2] - anchor_center[2]) * anchor_scale,
    )

    center_delta_in_anchor = _mat3_vec_mul(anchor_rot, center_delta_scene)
    source_z_bias = _mat3_vec_mul(rotation_scaled, (0.0, 0.0, source_z_offset))
    translation = (
        center_delta_in_anchor[0] + source_z_bias[0],
        center_delta_in_anchor[1] + source_z_bias[1],
        center_delta_in_anchor[2] + source_z_bias[2] - anchor_z_offset,
    )

    return Matrix((
        (rotation_scaled[0][0], rotation_scaled[0][1], rotation_scaled[0][2], translation[0]),
        (rotation_scaled[1][0], rotation_scaled[1][1], rotation_scaled[1][2], translation[1]),
        (rotation_scaled[2][0], rotation_scaled[2][1], rotation_scaled[2][2], translation[2]),
        (0.0, 0.0, 0.0, 1.0),
    )), ""


def _is_already_aligned_to_anchor(source_obj, anchor_source):
    source_anchor = str(source_obj.get("fg_btg_anchor_source", ""))
    if not anchor_source or not source_anchor:
        return False
    return os.path.abspath(source_anchor) == os.path.abspath(anchor_source)


def _mark_object_anchor_alignment(source_obj, anchor_obj):
    anchor_source = str(anchor_obj.get("fg_btg_source", ""))
    if anchor_source:
        source_obj["fg_btg_anchor_source"] = os.path.abspath(anchor_source)

    source_obj["fg_btg_exportable_reference"] = True
    source_obj["fg_btg_anchor_center_x"] = float(anchor_obj.get("fg_btg_center_x", 0.0))
    source_obj["fg_btg_anchor_center_y"] = float(anchor_obj.get("fg_btg_center_y", 0.0))
    source_obj["fg_btg_anchor_center_z"] = float(anchor_obj.get("fg_btg_center_z", 0.0))

    for child in getattr(source_obj, "children", []):
        if child.type != "MESH" or not child.get("fg_btg_is_point_group"):
            continue
        if anchor_source:
            child["fg_btg_anchor_source"] = os.path.abspath(anchor_source)
        child["fg_btg_exportable_reference"] = True
        child["fg_btg_anchor_center_x"] = source_obj["fg_btg_anchor_center_x"]
        child["fg_btg_anchor_center_y"] = source_obj["fg_btg_anchor_center_y"]
        child["fg_btg_anchor_center_z"] = source_obj["fg_btg_anchor_center_z"]


def _btg_center_from_tile_index(tile_index):
    bucket = _bucket_from_index(int(tile_index))
    center_lon, center_lat = _bucket_center_lon_lat(bucket)
    return _geodetic_to_ecef(center_lon, center_lat, 0.0)


def _retarget_btg_source_path(source_path, tile_index):
    normalized_source = os.path.abspath(str(source_path or ""))
    extension = ".btg.gz" if normalized_source.lower().endswith(".btg.gz") else ".btg"
    target_basename = f"{int(tile_index)}{extension}"

    current_tile_index = _tile_index_from_path(normalized_source)
    source_dir = os.path.dirname(normalized_source) if normalized_source else ""
    if current_tile_index is not None and source_dir:
        current_bucket_tail = os.path.normpath(_bucket_base_path(_bucket_from_index(current_tile_index)))
        normalized_dir = os.path.normpath(source_dir)
        if normalized_dir.endswith(current_bucket_tail):
            bucket_root = os.path.dirname(os.path.dirname(source_dir))
            return os.path.join(bucket_root, _bucket_base_path(_bucket_from_index(tile_index)), target_basename)

    if source_dir:
        return os.path.join(source_dir, target_basename)
    return target_basename


def _retarget_tile_object_name(name, old_tile_index, new_tile_index):
    if not isinstance(name, str) or not name:
        return name

    old_label = str(old_tile_index)
    new_label = str(new_tile_index)
    if name == old_label or name.startswith(old_label + ".") or name.startswith(old_label + "_lights"):
        return new_label + name[len(old_label):]
    return name


def _tile_metadata_status(anchor_obj):
    source_path = str(anchor_obj.get("fg_btg_source", ""))
    tile_index = _tile_index_from_path(source_path)
    if tile_index is None:
        return None, None, "No numeric tile index in fg_btg_source"

    stored_center = (
        float(anchor_obj.get("fg_btg_center_x", 0.0)),
        float(anchor_obj.get("fg_btg_center_y", 0.0)),
        float(anchor_obj.get("fg_btg_center_z", 0.0)),
    )
    expected_center = _btg_center_from_tile_index(tile_index)
    center_error_m = math.sqrt(
        (stored_center[0] - expected_center[0]) * (stored_center[0] - expected_center[0])
        + (stored_center[1] - expected_center[1]) * (stored_center[1] - expected_center[1])
        + (stored_center[2] - expected_center[2]) * (stored_center[2] - expected_center[2])
    )
    if center_error_m <= 1.0:
        status_label = f"Center Status: OK ({center_error_m:.3f} m error)"
    else:
        status_label = f"Center Status: Mismatch ({center_error_m:.1f} m error)"
    return tile_index, center_error_m, status_label


def _draw_collapsible_section(layout, scene, property_name, label):
    box = layout.box()
    expanded = bool(getattr(scene, property_name, True))
    header = box.row()
    header.prop(
        scene,
        property_name,
        text="",
        icon="TRIA_DOWN" if expanded else "TRIA_RIGHT",
        emboss=False,
    )
    header.label(text=label)
    return box, expanded


def _adjacent_reference_objects_for_anchor(scene, anchor_obj):
    anchor_source = os.path.abspath(str(anchor_obj.get("fg_btg_source", "")))
    matches = []
    for obj in scene.objects:
        if not obj.get("fg_btg_is_adjacent_reference"):
            continue
        obj_anchor = str(obj.get("fg_btg_anchor_source", ""))
        if obj_anchor and os.path.abspath(obj_anchor) == anchor_source:
            matches.append(obj)
    return matches


def _adjacent_reference_mesh_objects_for_anchor(scene, anchor_obj):
    return [
        obj
        for obj in _adjacent_reference_objects_for_anchor(scene, anchor_obj)
        if obj.type == "MESH" and not obj.get("fg_btg_is_point_group")
    ]


def _adjacent_display_summary(objects):
    if not objects:
        return "None", "Off", "Unlocked"

    display_types = {str(getattr(obj, "display_type", "SOLID")) for obj in objects}
    show_in_front_values = {bool(getattr(obj, "show_in_front", False)) for obj in objects}
    hide_select_values = {bool(getattr(obj, "hide_select", False)) for obj in objects}

    if len(display_types) == 1:
        display_label = next(iter(display_types)).title()
    else:
        display_label = "Mixed"

    if len(show_in_front_values) == 1:
        front_label = "On" if next(iter(show_in_front_values)) else "Off"
    else:
        front_label = "Mixed"

    if len(hide_select_values) == 1:
        select_label = "Locked" if next(iter(hide_select_values)) else "Unlocked"
    else:
        select_label = "Mixed"

    return display_label, front_label, select_label


def _set_adjacent_display_state(scene, anchor_obj, display_type=None, show_in_front=None, hide_select=None):
    updated = 0
    for obj in _adjacent_reference_mesh_objects_for_anchor(scene, anchor_obj):
        if display_type is not None:
            obj.display_type = display_type
        if show_in_front is not None:
            obj.show_in_front = bool(show_in_front)
        if hide_select is not None:
            obj.hide_select = bool(hide_select)
        updated += 1
    return updated


def _remove_objects_and_unused_meshes(objects):
    if bpy is None:
        return 0

    ordered = list(objects)
    mesh_data = []
    for obj in ordered:
        if getattr(obj, "data", None) is not None:
            mesh_data.append(obj.data)
        bpy.data.objects.remove(obj, do_unlink=True)

    removed_meshes = 0
    seen_meshes = set()
    for mesh in mesh_data:
        if mesh is None:
            continue
        ptr = mesh.as_pointer()
        if ptr in seen_meshes:
            continue
        seen_meshes.add(ptr)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
            removed_meshes += 1

    return removed_meshes


def _remove_empty_collection(collection):
    if bpy is None or collection is None:
        return
    if collection.objects or collection.children:
        return

    for parent in bpy.data.collections:
        if any(child == collection for child in parent.children):
            parent.children.unlink(collection)
    for scene in bpy.data.scenes:
        if any(child == collection for child in scene.collection.children):
            scene.collection.children.unlink(collection)
    if collection.users == 0:
        bpy.data.collections.remove(collection)


def _load_adjacent_reference_tiles(
    context,
    anchor_obj,
    texture_root,
    material_map_path,
    textured_materials=True,
    flip_dds_v_for_view=True,
    create_missing_ocean_placeholders=False,
):
    source_path = str(anchor_obj.get("fg_btg_source", ""))
    if not source_path:
        raise RuntimeError("Active tile does not have a BTG source path")
    if _tile_index_from_path(source_path) is None:
        raise RuntimeError(
            "Adjacent tile loading only works for numeric FlightGear bucket tiles such as 1745369.btg.gz."
        )

    adjacent_paths, missing_entries = _adjacent_btg_paths(source_path)
    anchor_source = os.path.abspath(source_path)
    existing_sources = {
        os.path.abspath(str(obj.get("fg_btg_source", "")))
        for obj in _adjacent_reference_objects_for_anchor(context.scene, anchor_obj)
        if str(obj.get("fg_btg_source", ""))
    }

    adjacent_collection = _ensure_child_collection(
        context.scene.collection,
        _adjacent_collection_name(anchor_obj),
    )
    anchor_center = (
        float(anchor_obj.get("fg_btg_center_x", 0.0)),
        float(anchor_obj.get("fg_btg_center_y", 0.0)),
        float(anchor_obj.get("fg_btg_center_z", 0.0)),
    )
    anchor_enu_rot = _ecef_to_enu_matrix(*anchor_center)
    anchor_z_offset = float(anchor_obj.get("fg_btg_z_offset", 0.0))

    adjacent_loaded = 0
    skipped_existing = 0
    placeholders_created = 0
    for adjacent_source_path in adjacent_paths:
        adjacent_btg_path = _decompress_btg_gz_to_folder(adjacent_source_path)
        adjacent_btg_path = os.path.abspath(adjacent_btg_path)
        if adjacent_btg_path in existing_sources:
            skipped_existing += 1
            continue

        adjacent_btg_data = parse_btg(adjacent_btg_path)
        if not adjacent_btg_data.vertices:
            continue

        adjacent_obj = _create_blender_mesh_object(
            context,
            adjacent_btg_path,
            adjacent_btg_data,
            texture_root,
            material_map_path,
            textured_materials=textured_materials,
            flip_dds_v_for_view=flip_dds_v_for_view,
            target_collection=adjacent_collection,
            select_imported=False,
            reference_center=anchor_center,
            reference_enu_rot=anchor_enu_rot,
            reference_z_offset=anchor_z_offset,
            is_adjacent_reference=True,
        )
        adjacent_obj["fg_btg_anchor_source"] = anchor_source
        for child in getattr(adjacent_obj, "children", []):
            child["fg_btg_anchor_source"] = anchor_source

        existing_sources.add(adjacent_btg_path)
        adjacent_loaded += 1

    if create_missing_ocean_placeholders:
        for entry in missing_entries:
            placeholder_path = str(entry.get("preferred_path", "") or "")
            if placeholder_path.lower().endswith(".gz"):
                placeholder_path = placeholder_path[:-3]
            if not placeholder_path:
                placeholder_path = os.path.join(
                    os.path.dirname(os.path.abspath(source_path)),
                    f"{entry.get('index', '')}.btg",
                )
            placeholder_path = os.path.abspath(placeholder_path)
            if placeholder_path in existing_sources:
                skipped_existing += 1
                continue

            bucket = entry.get("bucket") or _bucket_from_index(int(entry.get("index", 0)))
            placeholder_data = _placeholder_btg_data_for_bucket(bucket, material_name="ocean")
            placeholder_obj = _create_blender_mesh_object(
                context,
                placeholder_path,
                placeholder_data,
                texture_root,
                material_map_path,
                textured_materials=textured_materials,
                flip_dds_v_for_view=flip_dds_v_for_view,
                target_collection=adjacent_collection,
                select_imported=False,
                reference_center=anchor_center,
                reference_enu_rot=anchor_enu_rot,
                reference_z_offset=anchor_z_offset,
                is_adjacent_reference=True,
            )
            placeholder_obj["fg_btg_anchor_source"] = anchor_source
            placeholder_obj["fg_btg_is_generated_placeholder"] = True
            # Generated ocean placeholders are intentionally exportable so
            # creators can bootstrap entirely fictional scenery from empty sea.
            placeholder_obj["fg_btg_exportable_reference"] = True
            placeholder_obj["fg_btg_anchor_center_x"] = anchor_center[0]
            placeholder_obj["fg_btg_anchor_center_y"] = anchor_center[1]
            placeholder_obj["fg_btg_anchor_center_z"] = anchor_center[2]
            existing_sources.add(placeholder_path)
            placeholders_created += 1

    context.view_layer.objects.active = anchor_obj
    anchor_obj.select_set(True)
    return adjacent_loaded, skipped_existing, missing_entries, placeholders_created

class FlightGearBTGPreferences(AddonPreferences):
    bl_idname = ADDON_ID

    texture_root: str
    material_map_path: str

    def draw(self, context):
        del context
        self.layout.prop(self, "texture_root")
        self.layout.prop(self, "material_map_path")


class FlightGearMaterialSettings(PropertyGroup):
    pass


class MATERIAL_OT_flightgear_apply_preset(Operator):
    bl_idname = "material.flightgear_apply_preset"
    bl_label = "Apply FlightGear Preset"
    bl_description = "Apply preset defaults to the active Blender material's FlightGear export settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        material = getattr(context, "material", None)
        if material is None:
            self.report({"ERROR"}, "No active material.")
            return {"CANCELLED"}

        settings = _flightgear_material_settings(material)
        if settings is None:
            self.report({"ERROR"}, "FlightGear material settings are unavailable on this material.")
            return {"CANCELLED"}

        preset_name = str(getattr(settings, "preset", "CUSTOM") or "CUSTOM")
        if preset_name == "CUSTOM":
            settings.enabled = True
            self.report({"INFO"}, "FlightGear material overrides enabled for custom settings.")
            return {"FINISHED"}

        if not _apply_flightgear_material_preset(settings, preset_name):
            self.report({"ERROR"}, f"Unknown FlightGear material preset '{preset_name}'.")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Applied FlightGear preset '{preset_name.lower()}'.")
        return {"FINISHED"}


class MATERIAL_PT_flightgear_material(Panel):
    bl_label = "FlightGear"
    bl_idname = "MATERIAL_PT_flightgear_material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        material = context.material
        settings = _flightgear_material_settings(material)

        preview_box = layout.box()
        preview_box.label(text="Preview")
        preview_box.label(text=f"Export Name: {_material_export_name(material, _texture_root_from_context(context), _material_map_path_from_context(context))}")
        preview_box.label(text=f"Texture: {_flightgear_material_image_label(material)}")
        preview_box.label(text=f"Sync: {_flightgear_material_sync_status(material)}")
        if _is_flightgear_imported_material(material):
            source_name = str(material.get("fg_btg_material_name", material.name) or material.name)
            preview_box.label(text=f"Imported FG Name: {source_name}")

        if settings is None:
            layout.label(text="FlightGear settings are unavailable.")
            return

        layout.prop(settings, "enabled", text="Use FlightGear Material Overrides")

        preset_box = layout.box()
        preset_box.label(text="Material Type")
        preset_box.prop(settings, "preset", text="Preset")
        preset_box.operator(MATERIAL_OT_flightgear_apply_preset.bl_idname, text="Apply Preset Defaults")

        if not settings.enabled:
            layout.label(text="Enable overrides to export custom FlightGear material properties.")
            return

        surface_box = layout.box()
        surface_box.label(text="Surface")
        surface_box.prop(settings, "effect")
        surface_box.prop(settings, "xsize")
        surface_box.prop(settings, "ysize")
        surface_box.prop(settings, "wrapu")
        surface_box.prop(settings, "wrapv")

        physical_box = layout.box()
        physical_box.label(text="Physical / Sim")
        physical_box.prop(settings, "override_solid")
        if settings.override_solid:
            physical_box.prop(settings, "solid")
        physical_box.prop(settings, "override_physics")
        if settings.override_physics:
            physical_box.prop(settings, "friction_factor")
            physical_box.prop(settings, "rolling_friction")
            physical_box.prop(settings, "bumpiness")
            physical_box.prop(settings, "load_resistance")


def write_obj(
    filepath,
    vertices,
    faces,
    scale=1.0,
    texcoords=None,
    face_texcoords=None,
    face_materials=None,
    texture_root=None,
    material_map_path="",
):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Auto-generated from FlightGear BTG\n")
        texcoords = texcoords or []
        face_texcoords = face_texcoords or []
        face_materials = face_materials or []
        material_names = sorted({name for name in face_materials if name})
        material_map = {}
        if material_names and texture_root is not None:
            mtl_path = os.path.splitext(filepath)[0] + ".mtl"
            material_map = _write_mtl(mtl_path, material_names, texture_root, material_map_path)
            f.write(f"mtllib {os.path.basename(mtl_path)}\n")
        f.write("o btg_tile\n")

        for vx, vy, vz in vertices:
            f.write(f"v {vx * scale:.9f} {vy * scale:.9f} {vz * scale:.9f}\n")

        for u, v in texcoords:
            f.write(f"vt {u:.9f} {v:.9f}\n")

        last_material = None
        for i, (a, b, c) in enumerate(faces):
            material = face_materials[i] if i < len(face_materials) else ""
            if material and material != last_material:
                f.write(f"g {_mtl_safe_name(material)}\n")
                if material in material_map:
                    f.write(f"usemtl {material_map[material]}\n")
                last_material = material

            if i < len(face_texcoords):
                ta, tb, tc = face_texcoords[i]
                if ta is not None and tb is not None and tc is not None and texcoords:
                    f.write(f"f {a + 1}/{ta + 1} {b + 1}/{tb + 1} {c + 1}/{tc + 1}\n")
                    continue

            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


class IMPORT_SCENE_OT_flightgear_btg(Operator, ImportHelper):
    bl_idname = "import_scene.flightgear_btg"
    bl_label = "Import FlightGear BTG"
    bl_description = "Import a FlightGear BTG tile, optionally creating textured materials and loading adjacent reference tiles"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".btg"
    filter_glob: str
    create_materials: bool
    texture_root: str
    flip_dds_v_for_view: bool
    load_adjacent_tiles: bool
    create_ocean_placeholders_for_missing_adjacent: bool

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "create_materials")
        if _resolved_bool_property(getattr(self, "create_materials", True), True):
            layout.prop(self, "texture_root")
        layout.prop(self, "flip_dds_v_for_view")
        layout.separator()
        layout.prop(self, "load_adjacent_tiles")
        if _resolved_bool_property(getattr(self, "load_adjacent_tiles", False), False):
            layout.prop(self, "create_ocean_placeholders_for_missing_adjacent")

    def execute(self, context):
        source_path = self.filepath

        try:
            btg_path = _decompress_btg_gz_to_folder(source_path)
            btg_data = parse_btg(btg_path)

            if not btg_data.vertices:
                self.report({"ERROR"}, "No vertices found in BTG file")
                return {"CANCELLED"}

            textured_materials = _resolved_bool_property(getattr(self, "create_materials", True), True)
            flip_dds_v_for_view = _resolved_bool_property(getattr(self, "flip_dds_v_for_view", True), True)
            load_adjacent_tiles = _resolved_bool_property(getattr(self, "load_adjacent_tiles", False), False)
            create_ocean_placeholders = _resolved_bool_property(
                getattr(self, "create_ocean_placeholders_for_missing_adjacent", False),
                False,
            )
            texture_override = _resolved_string_property(getattr(self, "texture_root", ""), "")
            texture_root = _texture_root_from_context(context, texture_override) if textured_materials else None
            material_map_path = _material_map_path_from_context(context)
            main_obj = _create_blender_mesh_object(
                context,
                btg_path,
                btg_data,
                texture_root,
                material_map_path,
                textured_materials=textured_materials,
                flip_dds_v_for_view=flip_dds_v_for_view,
            )

            adjacent_loaded = 0
            skipped_existing = 0
            missing_adjacent = []
            placeholders_created = 0
            if load_adjacent_tiles:
                try:
                    adjacent_loaded, skipped_existing, missing_adjacent, placeholders_created = _load_adjacent_reference_tiles(
                        context,
                        main_obj,
                        texture_root,
                        material_map_path,
                        textured_materials=textured_materials,
                        flip_dds_v_for_view=flip_dds_v_for_view,
                        create_missing_ocean_placeholders=create_ocean_placeholders,
                    )
                    unresolved_missing = max(0, len(missing_adjacent) - placeholders_created)
                    if unresolved_missing:
                        self.report(
                            {"WARNING"},
                            f"Loaded {adjacent_loaded} adjacent tiles; {unresolved_missing} neighbors were not found on disk.",
                        )
                    if placeholders_created:
                        self.report(
                            {"INFO"},
                            f"Created {placeholders_created} ocean placeholder tiles for missing neighbors.",
                        )
                    if skipped_existing:
                        self.report(
                            {"INFO"},
                            f"Skipped {skipped_existing} adjacent tiles that were already loaded for this anchor tile.",
                        )
                except Exception as adjacent_exc:
                    self.report({"WARNING"}, f"Imported main BTG, but adjacent tile loading failed: {adjacent_exc}")

            info_message = f"Imported BTG directly ({len(btg_data.vertices)} verts, {len(btg_data.faces)} tris) at 1% scale"
            total_adjacent = adjacent_loaded + placeholders_created
            if total_adjacent:
                info_message += f" + {total_adjacent} adjacent reference tiles"
            self.report(
                {"INFO"},
                info_message,
            )
            return {"FINISHED"}

        except Exception as exc:
            self.report({"ERROR"}, f"Failed to import BTG: {exc}")
            return {"CANCELLED"}


class EXPORT_SCENE_OT_flightgear_btg(Operator, ExportHelper):
    bl_idname = "export_scene.flightgear_btg"
    bl_label = "Export FlightGear BTG"
    bl_description = "Export selected BTG-tagged meshes to FlightGear BTG, with optional STG/materials.xml sync and scenery package layout copy"
    bl_options = {"REGISTER"}

    filename_ext = ".btg.gz"
    check_extension = False
    filter_glob: str
    export_selected: bool
    sync_materials_xml: bool
    write_associated_stg: bool
    export_scenery_package_layout: bool
    scenery_package_root: str
    materials_xml_path: str
    texture_subfolder: str
    overwrite_existing_materials: bool
    overwrite_texture_files: bool
    flip_dds_v_for_view: bool

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_selected")
        layout.prop(self, "flip_dds_v_for_view")
        layout.prop(self, "write_associated_stg")
        layout.prop(self, "export_scenery_package_layout")
        if _resolved_bool_property(getattr(self, "export_scenery_package_layout", False), False):
            layout.prop(self, "scenery_package_root")
            export_selected = _resolved_bool_property(getattr(self, "export_selected", True), True)
            preview_objects = list(context.selected_objects) if export_selected else list(context.scene.objects)
            preview_meshes = [obj for obj in preview_objects if obj.type == "MESH"]
            preview_path = _package_btg_destination_preview(
                _resolved_string_property(getattr(self, "filepath", ""), "").strip(),
                _resolved_string_property(getattr(self, "scenery_package_root", ""), "").strip(),
                preview_meshes,
            )
            if preview_path:
                preview_box = layout.box()
                preview_box.label(text="Scenery package target:")
                preview_box.label(text=preview_path)
        layout.separator()
        layout.prop(self, "sync_materials_xml")
        if _resolved_bool_property(getattr(self, "sync_materials_xml", True), True):
            layout.prop(self, "materials_xml_path")
            layout.prop(self, "texture_subfolder")
            layout.prop(self, "overwrite_existing_materials")
            layout.prop(self, "overwrite_texture_files")

    def execute(self, context):
        try:
            export_selected = _resolved_bool_property(getattr(self, "export_selected", True), True)
            sync_materials_xml = _resolved_bool_property(getattr(self, "sync_materials_xml", True), True)
            write_associated_stg = _resolved_bool_property(getattr(self, "write_associated_stg", True), True)
            export_scenery_package_layout = _resolved_bool_property(
                getattr(self, "export_scenery_package_layout", False),
                False,
            )
            scenery_package_root = _resolved_string_property(getattr(self, "scenery_package_root", ""), "").strip()
            materials_xml_override = _resolved_string_property(getattr(self, "materials_xml_path", ""), "").strip()
            texture_subfolder = _resolved_string_property(getattr(self, "texture_subfolder", "bfg-exporter"), "bfg-exporter").strip()
            overwrite_existing_materials = _resolved_bool_property(
                getattr(self, "overwrite_existing_materials", False),
                False,
            )
            overwrite_texture_files = _resolved_bool_property(
                getattr(self, "overwrite_texture_files", False),
                False,
            )
            flip_dds_v_for_view = _resolved_bool_property(getattr(self, "flip_dds_v_for_view", True), True)

            export_objects = list(context.selected_objects) if export_selected else list(context.scene.objects)
            export_meshes = [obj for obj in export_objects if obj.type == "MESH"]
            if _has_adjacent_reference_tiles(export_meshes):
                self.report(
                    {"ERROR"},
                    "Adjacent reference tiles are imported in the active tile's local frame for snapping only and cannot be exported directly. Export the main tile object instead.",
                )
                return {"CANCELLED"}

            (
                mesh_objects,
                vertices,
                normals,
                faces,
                texcoords,
                face_uv_indices,
                face_materials,
                point_groups,
            ) = _extract_export_mesh_data(
                context,
                export_selected,
                coordinate_scale=EXPORT_SCALE,
                apply_enu_inverse=True,
                preserve_btg_local_frame=True,
                reverse_dds_view_flip=flip_dds_v_for_view,
                texture_root=_texture_root_from_context(context),
                material_map_path=_material_map_path_from_context(context),
                materials_xml_override=materials_xml_override,
            )
            if not mesh_objects:
                self.report({"ERROR"}, "No mesh objects found to export")
                return {"CANCELLED"}
            if not vertices or not faces:
                self.report({"ERROR"}, "No triangulated mesh data available for export")
                return {"CANCELLED"}

            expected_points = 0
            for source_obj in mesh_objects:
                if source_obj.get("fg_btg_is_point_group"):
                    continue
                expected_points += int(source_obj.get("fg_btg_original_point_count", 0))
            exported_points = _point_group_vertex_count(point_groups)
            if expected_points > 0 and exported_points < expected_points:
                self.report(
                    {"WARNING"},
                    (
                        "Detected fewer BTG point vertices than the original import "
                        f"({exported_points} exported vs {expected_points} original). "
                        "Airport light points may have been deleted."
                    ),
                )

            if _has_mixed_btg_centers(mesh_objects):
                self.report(
                    {"ERROR"},
                    "Selected meshes come from different BTG tile centers. Export one tile/object at a time.",
                )
                return {"CANCELLED"}

            if _has_untagged_meshes_for_btg_export(mesh_objects):
                self.report(
                    {"ERROR"},
                    "Selection includes meshes without BTG tile metadata. Join edits back to the imported BTG object or export only tagged BTG meshes.",
                )
                return {"CANCELLED"}

            center = _center_from_objects(mesh_objects)
            output_tile_index = _tile_index_from_path(self.filepath)
            source_basename = _source_basename_for_objects(mesh_objects)
            if output_tile_index is not None and source_basename and source_basename.isdigit():
                source_tile_index = int(source_basename)
                if output_tile_index != source_tile_index:
                    self.report(
                        {"ERROR"},
                        (
                            "Output filename tile index does not match the imported BTG tile metadata: "
                            f"exporting as '{output_tile_index}' but selected mesh data comes from '{source_tile_index}'. "
                            "This would write terrain with the wrong bucket center and usually appears as a blank tile in FlightGear. "
                            "Export using the source tile index, or transfer your edits onto the correct imported tile first."
                        ),
                    )
                    return {"CANCELLED"}

            if output_tile_index is not None:
                expected_bucket = _bucket_from_index(output_tile_index)
                expected_lon, expected_lat = _bucket_center_lon_lat(expected_bucket)
                expected_center = _geodetic_to_ecef(expected_lon, expected_lat, 0.0)
                center_error_m = math.sqrt(
                    (center[0] - expected_center[0]) * (center[0] - expected_center[0])
                    + (center[1] - expected_center[1]) * (center[1] - expected_center[1])
                    + (center[2] - expected_center[2]) * (center[2] - expected_center[2])
                )
                if center_error_m > 1000.0:
                    self.report(
                        {"ERROR"},
                        (
                            f"Stored BTG center is {center_error_m:.1f} m away from the expected center for tile '{output_tile_index}'. "
                            "This usually means the mesh was joined with geometry from another imported tile and kept the wrong fg_btg_center metadata. "
                            "Reimport the correct tile and transfer the edits, or update the BTG center metadata before exporting."
                        ),
                    )
                    return {"CANCELLED"}

            cx, cy, cz = center
            # _extract_export_mesh_data returns ECEF-relative offsets (metres).
            # write_btg expects absolute ECEF and subtracts center internally,
            # so we add the tile center back here.
            vertices_abs = [(vx + cx, vy + cy, vz + cz) for vx, vy, vz in vertices]

            out_path = self.filepath
            write_path = out_path[:-3] if out_path.lower().endswith(".gz") else out_path
            write_btg(
                write_path,
                vertices_abs,
                normals,
                faces,
                face_uv_indices=face_uv_indices,
                texcoords=texcoords,
                face_materials=face_materials,
                point_groups=point_groups,
                center=center,
                version=10,
            )

            if out_path.lower().endswith(".gz"):
                with open(write_path, "rb") as src, gzip.open(out_path, "wb") as dst:
                    dst.write(src.read())

            exported_btg_path = out_path if out_path.lower().endswith(".gz") else write_path
            exported_btg_name = os.path.basename(exported_btg_path)

            stg_note = ""
            if write_associated_stg:
                try:
                    stg_path = _stg_path_for_btg_export(out_path)
                    stg_status = _upsert_stg_object_base(stg_path, exported_btg_name)
                    stg_note = f"; STG {stg_status}: {os.path.basename(stg_path)}"
                except Exception as stg_exc:
                    self.report({"WARNING"}, f"BTG exported, but STG update failed: {stg_exc}")

            package_note = ""
            if export_scenery_package_layout:
                try:
                    if not scenery_package_root:
                        raise RuntimeError("Scenery Package Root is required when package layout export is enabled")

                    tile_index = _tile_index_from_path(exported_btg_path)
                    if tile_index is None:
                        source_basename = _source_basename_for_objects(mesh_objects)
                        if source_basename and source_basename.isdigit():
                            tile_index = int(source_basename)
                    if tile_index is None:
                        raise RuntimeError(
                            "Could not determine numeric tile index for package layout. "
                            "Name the output file as a FlightGear tile index (for example 1940177.btg.gz)."
                        )

                    bucket = _bucket_from_index(tile_index)
                    bucket_dir = os.path.join(
                        os.path.abspath(scenery_package_root),
                        "Terrain",
                        _bucket_base_path(bucket),
                    )
                    os.makedirs(bucket_dir, exist_ok=True)

                    packaged_btg_name = f"{tile_index}.btg.gz" if exported_btg_name.lower().endswith(".gz") else f"{tile_index}.btg"
                    packaged_btg_path = os.path.join(bucket_dir, packaged_btg_name)
                    shutil.copy2(exported_btg_path, packaged_btg_path)

                    packaged_stg_path = _stg_path_for_btg_export(packaged_btg_path)
                    packaged_stg_status = _upsert_stg_object_base(packaged_stg_path, packaged_btg_name)
                    package_note = (
                        f"; package: {os.path.basename(packaged_btg_path)} + "
                        f"{os.path.basename(packaged_stg_path)} ({packaged_stg_status})"
                    )
                except Exception as package_exc:
                    self.report({"WARNING"}, f"BTG exported, but scenery package export failed: {package_exc}")

            material_sync_note = ""
            if sync_materials_xml:
                try:
                    texture_root = _texture_root_from_context(context)
                    fg_root = _infer_fg_root(texture_root)
                    if not fg_root:
                        raise RuntimeError(
                            "Could not infer FG_ROOT from Texture Root preference. "
                            "Set Terrain Texture Root to a path under FG_ROOT/Textures."
                        )

                    materials_xml_path = materials_xml_override or _default_materials_xml_path(texture_root)
                    if not materials_xml_path:
                        raise RuntimeError("Could not resolve target materials.xml path")

                    exported_names = []
                    seen = set()
                    for name in face_materials:
                        normalized = name or "Default"
                        if normalized not in seen:
                            seen.add(normalized)
                            exported_names.append(normalized)

                    material_map_path = _material_map_path_from_context(context)
                    material_usage = _material_usage_from_mesh_objects(
                        mesh_objects,
                        exported_names,
                        texture_root,
                        material_map_path,
                    )

                    new_entries = {}
                    material_texture_map = {}
                    copied_count = 0
                    skipped_no_texture = []
                    skipped_fg_native = []
                    for material_name in exported_names:
                        material = material_usage.get(material_name)
                        if material is None:
                            skipped_no_texture.append(material_name)
                            continue

                        # Keep FG-native imported materials out of the exporter
                        # managed section; only sync genuinely user-authored ones.
                        is_native_imported = _is_flightgear_imported_material(material)
                        has_custom_override, _image_path, _fg_name = _material_custom_texture_override(
                            material,
                            texture_root,
                            material_map_path,
                        )
                        if is_native_imported and not has_custom_override:
                            skipped_fg_native.append(material_name)
                            continue

                        image_path = _first_image_texture_path(material)
                        if not image_path:
                            skipped_no_texture.append(material_name)
                            continue

                        texture_rel, _dest = _copy_material_texture(
                            image_path,
                            fg_root,
                            texture_subfolder,
                            overwrite_existing=overwrite_texture_files,
                        )
                        if not texture_rel:
                            skipped_no_texture.append(material_name)
                            continue

                        copied_count += 1
                        new_entries[material_name] = _material_xml_settings_from_blender_material(
                            material,
                            texture_rel,
                        )
                        material_texture_map[material_name] = texture_rel

                    sync_result = _upsert_exporter_materials_xml(
                        materials_xml_path,
                        new_entries,
                        overwrite_existing=overwrite_existing_materials,
                    )

                    skipped_existing = sync_result["skipped_existing"]
                    if skipped_existing:
                        self.report(
                            {"WARNING"},
                            "Materials already existed and were not overwritten: "
                            + ", ".join(sorted(skipped_existing))
                            + ". Enable 'Overwrite Existing Materials' to replace them.",
                        )

                    if skipped_no_texture:
                        self.report(
                            {"WARNING"},
                            "Skipped materials without a readable image texture: "
                            + ", ".join(sorted(set(skipped_no_texture))),
                        )

                    if skipped_fg_native:
                        self.report(
                            {"INFO"},
                            "Skipped FlightGear-native imported materials from managed materials.xml sync: "
                            + ", ".join(sorted(set(skipped_fg_native))),
                        )

                    if material_texture_map:
                        self.report(
                            {"INFO"},
                            "Material texture bindings: "
                            + _format_material_sync_pairs(material_texture_map),
                        )

                    skip_parts = []
                    if skipped_existing:
                        skip_parts.append(f"existing={len(skipped_existing)}")
                    if skipped_no_texture:
                        skip_parts.append(f"no-texture={len(set(skipped_no_texture))}")
                    if skipped_fg_native:
                        skip_parts.append(f"native={len(set(skipped_fg_native))}")
                    if skip_parts:
                        self.report({"INFO"}, "Material sync skips: " + ", ".join(skip_parts))

                    material_sync_note = (
                        f"; material sync: {len(sync_result['inserted'])} new, "
                        f"{len(sync_result['updated'])} updated, {copied_count} textures copied"
                    )
                except Exception as material_exc:
                    self.report({"WARNING"}, f"BTG exported, but material sync failed: {material_exc}")

            self.report(
                {"INFO"},
                (
                    f"Exported BTG ({len(vertices)} verts, {len(faces)} tris) "
                    f"with implicit x100 scale{stg_note}{package_note}{material_sync_note}"
                ),
            )
            return {"FINISHED"}

        except Exception as exc:
            self.report({"ERROR"}, f"Failed to export BTG: {exc}")
            return {"CANCELLED"}


class EXPORT_SCENE_OT_wavefront_obj(Operator, ExportHelper):
    bl_idname = "export_scene.flightgear_obj"
    bl_label = "Export Wavefront OBJ"
    bl_description = "Export mesh geometry to Wavefront OBJ with optional BTG scale compensation and texture references"
    bl_options = {"REGISTER"}

    filename_ext = ".obj"
    filter_glob: str
    export_selected: bool
    apply_btg_scale: bool
    include_textures: bool

    def execute(self, context):
        try:
            export_selected = _resolved_bool_property(getattr(self, "export_selected", True), True)
            apply_btg_scale = _resolved_bool_property(getattr(self, "apply_btg_scale", False), False)
            include_textures = _resolved_bool_property(getattr(self, "include_textures", True), True)
            coordinate_scale = EXPORT_SCALE if apply_btg_scale else 1.0

            (
                mesh_objects,
                vertices,
                _normals,
                faces,
                texcoords,
                face_uv_indices,
                face_materials,
                _point_groups,
            ) = _extract_export_mesh_data(
                context,
                export_selected,
                coordinate_scale=coordinate_scale,
                texture_root=_texture_root_from_context(context),
                material_map_path=_material_map_path_from_context(context),
            )

            if not mesh_objects:
                self.report({"ERROR"}, "No mesh objects found to export")
                return {"CANCELLED"}
            if not vertices or not faces:
                self.report({"ERROR"}, "No triangulated mesh data available for export")
                return {"CANCELLED"}

            texture_root = _texture_root_from_context(context) if include_textures else None
            material_map_path = _material_map_path_from_context(context) if include_textures else ""

            write_obj(
                self.filepath,
                vertices,
                faces,
                scale=1.0,
                texcoords=texcoords,
                face_texcoords=face_uv_indices,
                face_materials=face_materials,
                texture_root=texture_root,
                material_map_path=material_map_path,
            )

            scale_note = " with x100 BTG scale compensation" if apply_btg_scale else ""
            self.report(
                {"INFO"},
                f"Exported OBJ ({len(vertices)} verts, {len(faces)} tris){scale_note}",
            )
            return {"FINISHED"}

        except Exception as exc:
            self.report({"ERROR"}, f"Failed to export OBJ: {exc}")
            return {"CANCELLED"}


class OBJECT_OT_flightgear_load_adjacent_tiles(Operator):
    bl_idname = "object.flightgear_load_adjacent_tiles"
    bl_label = "Load Adjacent FlightGear Tiles"
    bl_description = "Load the 8 neighboring FlightGear tiles around the active BTG tile for seam alignment and reference"
    bl_options = {"REGISTER", "UNDO"}

    flip_dds_v_for_view: bool
    create_ocean_placeholders_for_missing_adjacent: bool

    def draw(self, _context):
        self.layout.prop(self, "flip_dds_v_for_view")
        self.layout.prop(self, "create_ocean_placeholders_for_missing_adjacent")

    def execute(self, context):
        try:
            anchor_obj, error_message = _resolve_anchor_tile_object(context)
            if anchor_obj is None:
                self.report({"ERROR"}, error_message)
                return {"CANCELLED"}

            texture_root = _texture_root_from_context(context)
            material_map_path = _material_map_path_from_context(context)
            flip_dds_v_for_view = _resolved_bool_property(getattr(self, "flip_dds_v_for_view", True), True)
            create_ocean_placeholders = _resolved_bool_property(
                getattr(self, "create_ocean_placeholders_for_missing_adjacent", False),
                False,
            )
            adjacent_loaded, skipped_existing, missing_adjacent, placeholders_created = _load_adjacent_reference_tiles(
                context,
                anchor_obj,
                texture_root,
                material_map_path,
                textured_materials=True,
                flip_dds_v_for_view=flip_dds_v_for_view,
                create_missing_ocean_placeholders=create_ocean_placeholders,
            )

            unresolved_missing = max(0, len(missing_adjacent) - placeholders_created)
            if unresolved_missing:
                self.report(
                    {"WARNING"},
                    f"Loaded {adjacent_loaded} adjacent tiles; {unresolved_missing} neighbors were not found on disk.",
                )
            if placeholders_created:
                self.report(
                    {"INFO"},
                    f"Created {placeholders_created} ocean placeholder tiles for missing neighbors.",
                )
            if skipped_existing:
                self.report(
                    {"INFO"},
                    f"Skipped {skipped_existing} adjacent tiles that were already loaded for this anchor tile.",
                )
            total_loaded = adjacent_loaded + placeholders_created
            if total_loaded == 0 and skipped_existing == 0:
                self.report({"WARNING"}, "No adjacent tiles were loaded.")
                return {"CANCELLED"}

            self.report({"INFO"}, f"Loaded {total_loaded} adjacent reference tiles.")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to load adjacent tiles: {exc}")
            return {"CANCELLED"}


class OBJECT_OT_flightgear_clear_adjacent_tiles(Operator):
    bl_idname = "object.flightgear_clear_adjacent_tiles"
    bl_label = "Remove Adjacent FlightGear Tiles"
    bl_description = "Remove previously loaded adjacent reference tiles for the active BTG tile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        adjacent_objects = _adjacent_reference_objects_for_anchor(context.scene, anchor_obj)
        if not adjacent_objects:
            self.report({"INFO"}, "No adjacent reference tiles are loaded for the active tile.")
            return {"CANCELLED"}

        adjacent_collection = bpy.data.collections.get(_adjacent_collection_name(anchor_obj)) if bpy is not None else None
        removed_meshes = _remove_objects_and_unused_meshes(adjacent_objects)
        _remove_empty_collection(adjacent_collection)
        context.view_layer.objects.active = anchor_obj
        anchor_obj.select_set(True)

        self.report(
            {"INFO"},
            f"Removed {len(adjacent_objects)} adjacent reference objects and {removed_meshes} unused meshes.",
        )
        return {"FINISHED"}


class OBJECT_OT_flightgear_adjacent_display_mode(Operator):
    bl_idname = "object.flightgear_adjacent_display_mode"
    bl_label = "Set Adjacent Tile Display"
    bl_description = "Set viewport shading mode for loaded adjacent reference tiles"
    bl_options = {"REGISTER", "UNDO"}

    display_mode: str

    def execute(self, context):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        display_mode = _resolved_string_property(getattr(self, "display_mode", "SOLID"), "SOLID")
        updated = _set_adjacent_display_state(context.scene, anchor_obj, display_type=display_mode)
        if updated == 0:
            self.report({"INFO"}, "No adjacent reference tiles are loaded for the active tile.")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Updated {updated} adjacent reference tiles to {display_mode.lower()} display.")
        return {"FINISHED"}


class OBJECT_OT_flightgear_adjacent_show_in_front(Operator):
    bl_idname = "object.flightgear_adjacent_show_in_front"
    bl_label = "Set Adjacent Tiles In Front"
    bl_description = "Toggle draw-in-front for loaded adjacent reference tiles"
    bl_options = {"REGISTER", "UNDO"}

    show_in_front: bool

    def execute(self, context):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        show_in_front = _resolved_bool_property(getattr(self, "show_in_front", False), False)
        updated = _set_adjacent_display_state(context.scene, anchor_obj, show_in_front=show_in_front)
        if updated == 0:
            self.report({"INFO"}, "No adjacent reference tiles are loaded for the active tile.")
            return {"CANCELLED"}

        state_label = "enabled" if show_in_front else "disabled"
        self.report({"INFO"}, f"{state_label.capitalize()} in-front display for {updated} adjacent reference tiles.")
        return {"FINISHED"}


class OBJECT_OT_flightgear_adjacent_selectable(Operator):
    bl_idname = "object.flightgear_adjacent_selectable"
    bl_label = "Set Adjacent Tile Selectability"
    bl_description = "Lock or unlock selection for loaded adjacent reference tiles"
    bl_options = {"REGISTER", "UNDO"}

    selectable: bool

    def execute(self, context):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        selectable = _resolved_bool_property(getattr(self, "selectable", True), True)
        updated = _set_adjacent_display_state(context.scene, anchor_obj, hide_select=not selectable)
        if updated == 0:
            self.report({"INFO"}, "No adjacent reference tiles are loaded for the active tile.")
            return {"CANCELLED"}

        state_label = "unlocked" if selectable else "locked"
        self.report({"INFO"}, f"{state_label.capitalize()} selection for {updated} adjacent reference tiles.")
        return {"FINISHED"}


class OBJECT_OT_flightgear_adjacent_edit_preset(Operator):
    bl_idname = "object.flightgear_adjacent_edit_preset"
    bl_label = "Apply Adjacent Seam Edit Preset"
    bl_description = "Apply a seam-editing preset (wire, in-front, locked) to adjacent reference tiles"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        updated = _set_adjacent_display_state(
            context.scene,
            anchor_obj,
            display_type="WIRE",
            show_in_front=True,
            hide_select=True,
        )
        if updated == 0:
            self.report({"INFO"}, "No adjacent reference tiles are loaded for the active tile.")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Applied seam editing preset to {updated} adjacent reference tiles.",
        )
        return {"FINISHED"}


class OBJECT_OT_flightgear_retarget_tile(Operator):
    bl_idname = "object.flightgear_retarget_tile"
    bl_label = "Retarget Tile"
    bl_description = "Recalculate BTG tile metadata from a FlightGear tile index so the active mesh exports in a new bucket"
    bl_options = {"REGISTER", "UNDO"}

    target_tile_index: int
    rename_objects: bool

    def invoke(self, context, _event):
        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        source_path = str(anchor_obj.get("fg_btg_source", ""))
        current_tile_index = _tile_index_from_path(source_path)
        if current_tile_index is not None and not int(getattr(self, "target_tile_index", 0) or 0):
            self.target_tile_index = current_tile_index

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "target_tile_index")
        layout.prop(self, "rename_objects")

    def execute(self, context):
        if bpy is None:
            self.report({"ERROR"}, "This operator requires Blender runtime")
            return {"CANCELLED"}

        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        target_tile_index = int(getattr(self, "target_tile_index", 0) or 0)
        if target_tile_index <= 0:
            self.report({"ERROR"}, "Enter a valid numeric FlightGear tile index.")
            return {"CANCELLED"}

        source_path = str(anchor_obj.get("fg_btg_source", ""))
        current_tile_index = _tile_index_from_path(source_path)
        new_source_path = _retarget_btg_source_path(source_path, target_tile_index)
        new_center = _btg_center_from_tile_index(target_tile_index)

        adjacent_objects = _adjacent_reference_objects_for_anchor(context.scene, anchor_obj)
        removed_adjacent = len(adjacent_objects)
        removed_meshes = 0
        if adjacent_objects:
            adjacent_collection = bpy.data.collections.get(_adjacent_collection_name(anchor_obj))
            removed_meshes = _remove_objects_and_unused_meshes(adjacent_objects)
            _remove_empty_collection(adjacent_collection)

        related_objects = [anchor_obj]
        related_objects.extend(
            child
            for child in anchor_obj.children
            if child.type == "MESH" and child.get("fg_btg_is_point_group")
        )

        old_anchor_name = anchor_obj.name
        rename_objects = _resolved_bool_property(getattr(self, "rename_objects", True), True)
        for obj in related_objects:
            obj["fg_btg_center_x"] = new_center[0]
            obj["fg_btg_center_y"] = new_center[1]
            obj["fg_btg_center_z"] = new_center[2]
            obj["fg_btg_source"] = new_source_path

            if rename_objects and current_tile_index is not None:
                new_name = _retarget_tile_object_name(obj.name, current_tile_index, target_tile_index)
                if new_name and new_name != obj.name:
                    obj.name = new_name

        if _scene_working_mesh_name(context.scene) == old_anchor_name:
            _set_scene_working_mesh_name(context.scene, anchor_obj.name)
        if _scene_reference_mesh_name(context.scene) == old_anchor_name:
            _set_scene_reference_mesh_name(context.scene, anchor_obj.name)

        context.view_layer.objects.active = anchor_obj
        anchor_obj.select_set(True)

        message = (
            f"Retargeted '{anchor_obj.name}' to tile '{target_tile_index}' and recalculated BTG center metadata."
        )
        if removed_adjacent:
            message += f" Removed {removed_adjacent} adjacent reference objects and {removed_meshes} unused meshes."
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_flightgear_align_objects_from_metadata(Operator):
    bl_idname = "object.flightgear_align_objects_from_metadata"
    bl_label = "Align Objects"
    bl_description = "Align selected BTG objects to the active tile using fg_btg_* metadata"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy is None or Matrix is None:
            self.report({"ERROR"}, "This operator requires Blender runtime")
            return {"CANCELLED"}

        anchor_obj, error_message = _resolve_anchor_tile_object(context)
        if anchor_obj is None:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        anchor_source = str(anchor_obj.get("fg_btg_source", ""))

        candidates = []
        seen = set()
        for selected in context.selected_objects:
            source_obj = selected
            if source_obj.get("fg_btg_is_point_group") and getattr(source_obj, "parent", None) is not None:
                source_obj = source_obj.parent
            if source_obj is None or source_obj == anchor_obj:
                continue
            if source_obj.type != "MESH":
                continue

            ptr = source_obj.as_pointer()
            if ptr in seen:
                continue
            seen.add(ptr)
            candidates.append(source_obj)

        if not candidates:
            self.report(
                {"ERROR"},
                "Select at least two imported BTG mesh objects and keep the anchor tile active.",
            )
            return {"CANCELLED"}

        aligned = 0
        skipped_already_aligned = 0
        skipped_errors = []
        for source_obj in candidates:
            if _is_already_aligned_to_anchor(source_obj, anchor_source):
                skipped_already_aligned += 1
                continue

            align_matrix, error = _metadata_alignment_matrix(source_obj, anchor_obj)
            if align_matrix is None:
                skipped_errors.append(error)
                continue

            source_obj.matrix_world = align_matrix
            _mark_object_anchor_alignment(source_obj, anchor_obj)
            aligned += 1

        if aligned == 0:
            details = f" ({skipped_errors[0]})" if skipped_errors else ""
            self.report(
                {"WARNING"},
                "No objects were aligned." + details,
            )
            return {"CANCELLED"}

        message = f"Aligned {aligned} object(s) to active tile '{anchor_obj.name}' using fg_btg_* metadata."
        if skipped_already_aligned:
            message += f" Skipped {skipped_already_aligned} already aligned object(s)."
        if skipped_errors:
            message += f" Skipped {len(skipped_errors)} object(s) missing metadata."
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_flightgear_set_working_mesh_from_active(Operator):
    bl_idname = "object.flightgear_set_working_mesh_from_active"
    bl_label = "Use Active As Working Mesh"
    bl_description = "Set the seam-conform working mesh from the active mesh object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_obj = getattr(context, "active_object", None)
        if active_obj is None:
            self.report({"ERROR"}, "No active object.")
            return {"CANCELLED"}

        if active_obj.get("fg_btg_is_point_group") and getattr(active_obj, "parent", None) is not None:
            active_obj = active_obj.parent

        if active_obj is None or active_obj.type != "MESH":
            self.report({"ERROR"}, "Active object must be a mesh.")
            return {"CANCELLED"}

        _set_scene_working_mesh_name(context.scene, active_obj.name)
        self.report({"INFO"}, f"Working mesh set to '{active_obj.name}'.")
        return {"FINISHED"}


class OBJECT_OT_flightgear_set_reference_mesh_from_selection(Operator):
    bl_idname = "object.flightgear_set_reference_mesh_from_selection"
    bl_label = "Use Selected As Reference Mesh"
    bl_description = "Set the seam-conform reference mesh from another selected mesh object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        working_name = _scene_working_mesh_name(context.scene)
        working_obj = _resolve_mesh_object_for_conform(context.scene, working_name)
        active_obj = getattr(context, "active_object", None)

        candidates = []
        for obj in context.selected_objects:
            candidate = obj
            if candidate.get("fg_btg_is_point_group") and getattr(candidate, "parent", None) is not None:
                candidate = candidate.parent
            if candidate is None or candidate.type != "MESH":
                continue
            if working_obj is not None and candidate == working_obj:
                continue
            if working_obj is None and active_obj is not None and candidate == active_obj:
                continue
            candidates.append(candidate)

        if not candidates:
            self.report({"ERROR"}, "Select another mesh object to use as reference mesh.")
            return {"CANCELLED"}

        reference_obj = candidates[0]
        _set_scene_reference_mesh_name(context.scene, reference_obj.name)
        self.report({"INFO"}, f"Reference mesh set to '{reference_obj.name}'.")
        return {"FINISHED"}


class OBJECT_OT_flightgear_conform_seam_vertices(Operator):
    bl_idname = "object.flightgear_conform_seam_vertices"
    bl_label = "Conform Selected Seam Vertices"
    bl_description = "Conform working mesh seam vertices to a picked reference mesh (or loaded adjacent references) within a horizontal tolerance"
    bl_options = {"REGISTER", "UNDO"}

    working_tile_name: str
    reference_tile_name: str
    target_vertices: str
    snap_mode: str
    horizontal_tolerance_m: float

    def invoke(self, context, _event):
        active_obj = getattr(context, "active_object", None)
        scene_working_name = _scene_working_mesh_name(context.scene)
        scene_reference_name = _scene_reference_mesh_name(context.scene)

        if not getattr(self, "working_tile_name", "") and scene_working_name:
            self.working_tile_name = scene_working_name
        if not getattr(self, "reference_tile_name", "") and scene_reference_name:
            self.reference_tile_name = scene_reference_name

        if active_obj is not None and active_obj.type == "MESH":
            if not getattr(self, "working_tile_name", ""):
                self.working_tile_name = active_obj.name

            if not getattr(self, "reference_tile_name", ""):
                for obj in context.selected_objects:
                    if obj == active_obj or obj.type != "MESH":
                        continue
                    self.reference_tile_name = obj.name
                    break

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop_search(self, "working_tile_name", context.scene, "objects", text="Working Mesh")
        layout.prop_search(self, "reference_tile_name", context.scene, "objects", text="Reference Mesh")
        layout.prop(self, "target_vertices")
        layout.prop(self, "snap_mode")
        layout.prop(self, "horizontal_tolerance_m")

    def execute(self, context):
        if bpy is None or bmesh is None or Vector is None:
            self.report({"ERROR"}, "This operator requires Blender runtime")
            return {"CANCELLED"}

        active_obj = context.active_object
        if active_obj is not None and active_obj.get("fg_btg_is_point_group") and getattr(active_obj, "parent", None) is not None:
            active_obj = active_obj.parent

        working_obj = _resolve_mesh_object_for_conform(context.scene, getattr(self, "working_tile_name", ""))
        if working_obj is None:
            working_obj = active_obj if active_obj is not None and active_obj.type == "MESH" else None

        if working_obj is None:
            self.report({"ERROR"}, "Set a valid working mesh tile/object.")
            return {"CANCELLED"}

        _set_scene_working_mesh_name(context.scene, working_obj.name)

        reference_obj = _resolve_mesh_object_for_conform(context.scene, getattr(self, "reference_tile_name", ""))
        reference_meshes = []
        if reference_obj is not None and reference_obj != working_obj:
            reference_meshes.append(reference_obj)
        else:
            # Backward-compatible fallback: if no explicit reference is picked,
            # use loaded adjacent reference tiles for the working tile.
            source_path = working_obj.get("fg_btg_source")
            if isinstance(source_path, str) and source_path and not working_obj.get("fg_btg_is_adjacent_reference"):
                reference_meshes = _adjacent_reference_mesh_objects_for_anchor(context.scene, working_obj)

        if not reference_meshes:
            for obj in context.selected_objects:
                if obj == working_obj or obj.type != "MESH":
                    continue
                if obj.get("fg_btg_is_point_group") and getattr(obj, "parent", None) is not None:
                    obj = obj.parent
                if obj is None or obj == working_obj or obj.type != "MESH":
                    continue
                reference_meshes.append(obj)

        # Keep deterministic order and deduplicate by object pointer.
        deduped = []
        seen_ptrs = set()
        for obj in reference_meshes:
            ptr = obj.as_pointer()
            if ptr in seen_ptrs:
                continue
            seen_ptrs.add(ptr)
            deduped.append(obj)
        reference_meshes = deduped

        if not reference_meshes:
            self.report(
                {"ERROR"},
                (
                    "No reference mesh found. Pick a Reference Mesh, or select a second mesh object, "
                    "or load adjacent tiles for an imported working tile."
                ),
            )
            return {"CANCELLED"}

        if reference_obj is not None and reference_obj != working_obj:
            _set_scene_reference_mesh_name(context.scene, reference_obj.name)

        target_vertices = _resolved_string_property(getattr(self, "target_vertices", "SELECTED"), "SELECTED")
        in_edit_mode = getattr(context, "mode", "") == "EDIT_MESH"
        if target_vertices == "SELECTED" and not in_edit_mode:
            self.report({"ERROR"}, "Selected-vertex mode requires Edit Mode on the working mesh.")
            return {"CANCELLED"}

        if in_edit_mode and context.active_object != working_obj:
            self.report({"ERROR"}, "In Edit Mode, make the working mesh the active object before conforming.")
            return {"CANCELLED"}

        tol_m = max(0.0, float(getattr(self, "horizontal_tolerance_m", 0.20)))
        tol_scene = tol_m * IMPORT_SCALE
        if tol_scene <= 0.0:
            self.report({"ERROR"}, "Horizontal tolerance must be greater than zero.")
            return {"CANCELLED"}

        snap_mode = _resolved_string_property(getattr(self, "snap_mode", "Z_ONLY"), "Z_ONLY")
        inv_world = working_obj.matrix_world.inverted()

        if in_edit_mode:
            bm = bmesh.from_edit_mesh(working_obj.data)
            if target_vertices == "BOUNDARY":
                target_verts = [vert for vert in bm.verts if any(edge.is_boundary for edge in vert.link_edges)]
            else:
                target_verts = [vert for vert in bm.verts if vert.select]
        else:
            bm = None
            if target_vertices != "BOUNDARY":
                self.report({"ERROR"}, "Object Mode only supports Boundary Vertices mode.")
                return {"CANCELLED"}

            bm_tmp = bmesh.new()
            try:
                bm_tmp.from_mesh(working_obj.data)
                target_indices = [
                    vert.index
                    for vert in bm_tmp.verts
                    if any(edge.is_boundary for edge in vert.link_edges)
                ]
            finally:
                bm_tmp.free()
            target_verts = [working_obj.data.vertices[idx] for idx in sorted(target_indices)]

        if not target_verts:
            if target_vertices == "BOUNDARY":
                self.report({"ERROR"}, "No boundary vertices found on the working mesh.")
            else:
                self.report({"ERROR"}, "No selected vertices on the working mesh.")
            return {"CANCELLED"}

        # Bucket adjacent seam candidates by XY cells so nearest lookup for
        # selected verts remains responsive even on dense airports.
        inv_cell = 1.0 / tol_scene
        candidate_cells = {}
        candidate_count = 0
        for ref_obj in reference_meshes:
            if ref_obj.type != "MESH" or ref_obj.data is None:
                continue
            world_mat = ref_obj.matrix_world
            for vert in ref_obj.data.vertices:
                world = world_mat @ vert.co
                key = (int(math.floor(world.x * inv_cell)), int(math.floor(world.y * inv_cell)))
                candidate_cells.setdefault(key, []).append((world.x, world.y, world.z))
                candidate_count += 1

        if candidate_count == 0:
            self.report({"ERROR"}, "Reference mesh has no vertices to match against.")
            return {"CANCELLED"}

        matched = 0
        unmatched = 0
        worst_horizontal_error_m = 0.0

        for vert in target_verts:
            world = working_obj.matrix_world @ vert.co
            cell_x = int(math.floor(world.x * inv_cell))
            cell_y = int(math.floor(world.y * inv_cell))

            best = None
            best_dxy_sq = tol_scene * tol_scene
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    candidates = candidate_cells.get((cell_x + dx, cell_y + dy), ())
                    for cx, cy, cz in candidates:
                        dxy = (cx - world.x, cy - world.y)
                        dxy_sq = dxy[0] * dxy[0] + dxy[1] * dxy[1]
                        if dxy_sq <= best_dxy_sq:
                            best_dxy_sq = dxy_sq
                            best = (cx, cy, cz)

            if best is None:
                unmatched += 1
                continue

            matched += 1
            worst_horizontal_error_m = max(worst_horizontal_error_m, math.sqrt(best_dxy_sq) / IMPORT_SCALE)

            if snap_mode == "XYZ":
                target_world = best
            else:
                target_world = (world.x, world.y, best[2])

            vert.co = inv_world @ Vector(target_world)

        if bm is not None:
            bmesh.update_edit_mesh(working_obj.data, loop_triangles=False, destructive=False)
        else:
            working_obj.data.update()

        if matched == 0:
            self.report(
                {"WARNING"},
                (
                    "No target vertices found a seam match within "
                    f"{tol_m:.3f} m horizontal tolerance."
                ),
            )
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            (
                f"Conformed {matched} seam vertices on '{working_obj.name}' ({unmatched} unmatched). "
                f"Worst horizontal match error: {worst_horizontal_error_m:.3f} m."
            ),
        )
        return {"FINISHED"}


class OBJECT_OT_flightgear_set_vertices_in_game_altitude(Operator):
    bl_idname = "object.flightgear_set_vertices_in_game_altitude"
    bl_label = "Set Vertices at a Specific In-Game Altitude"
    bl_description = "Set selected or boundary vertices on the working mesh to a specific in-game altitude in meters"
    bl_options = {"REGISTER", "UNDO"}

    working_tile_name: str
    target_vertices: str
    altitude_m: float

    def invoke(self, context, _event):
        active_obj = getattr(context, "active_object", None)
        scene_working_name = _scene_working_mesh_name(context.scene)

        if not getattr(self, "working_tile_name", "") and scene_working_name:
            self.working_tile_name = scene_working_name

        if active_obj is not None and active_obj.type == "MESH" and not getattr(self, "working_tile_name", ""):
            self.working_tile_name = active_obj.name

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop_search(self, "working_tile_name", context.scene, "objects", text="Working Mesh")
        layout.prop(self, "target_vertices")
        layout.prop(self, "altitude_m")

    def execute(self, context):
        if bpy is None or bmesh is None or Vector is None:
            self.report({"ERROR"}, "This operator requires Blender runtime")
            return {"CANCELLED"}

        active_obj = context.active_object
        if active_obj is not None and active_obj.get("fg_btg_is_point_group") and getattr(active_obj, "parent", None) is not None:
            active_obj = active_obj.parent

        working_obj = _resolve_mesh_object_for_conform(context.scene, getattr(self, "working_tile_name", ""))
        if working_obj is None:
            working_obj = active_obj if active_obj is not None and active_obj.type == "MESH" else None

        if working_obj is None:
            self.report({"ERROR"}, "Set a valid working mesh tile/object.")
            return {"CANCELLED"}

        _set_scene_working_mesh_name(context.scene, working_obj.name)

        target_vertices = _resolved_string_property(getattr(self, "target_vertices", "SELECTED"), "SELECTED")
        in_edit_mode = getattr(context, "mode", "") == "EDIT_MESH"
        if target_vertices == "SELECTED" and not in_edit_mode:
            self.report({"ERROR"}, "Selected-vertex mode requires Edit Mode on the working mesh.")
            return {"CANCELLED"}

        if in_edit_mode and context.active_object != working_obj:
            self.report({"ERROR"}, "In Edit Mode, make the working mesh the active object before setting altitude.")
            return {"CANCELLED"}

        inv_world = working_obj.matrix_world.inverted()
        target_altitude_m = float(getattr(self, "altitude_m", 0.0))
        obj_import_scale = float(working_obj.get("fg_btg_import_scale", IMPORT_SCALE))
        obj_z_offset = float(working_obj.get("fg_btg_z_offset", 0.0))
        if bool(working_obj.get("fg_btg_enu_applied")):
            target_altitude_scene = target_altitude_m * obj_import_scale - obj_z_offset
        else:
            target_altitude_scene = target_altitude_m * obj_import_scale

        if in_edit_mode:
            bm = bmesh.from_edit_mesh(working_obj.data)
            if target_vertices == "BOUNDARY":
                target_verts = [vert for vert in bm.verts if any(edge.is_boundary for edge in vert.link_edges)]
            else:
                target_verts = [vert for vert in bm.verts if vert.select]
        else:
            bm = None
            if target_vertices != "BOUNDARY":
                self.report({"ERROR"}, "Object Mode only supports Boundary Vertices mode.")
                return {"CANCELLED"}

            bm_tmp = bmesh.new()
            try:
                bm_tmp.from_mesh(working_obj.data)
                target_indices = [
                    vert.index
                    for vert in bm_tmp.verts
                    if any(edge.is_boundary for edge in vert.link_edges)
                ]
            finally:
                bm_tmp.free()
            target_verts = [working_obj.data.vertices[idx] for idx in sorted(target_indices)]

        if not target_verts:
            if target_vertices == "BOUNDARY":
                self.report({"ERROR"}, "No boundary vertices found on the working mesh.")
            else:
                self.report({"ERROR"}, "No selected vertices on the working mesh.")
            return {"CANCELLED"}

        aligned = 0
        for vert in target_verts:
            world = working_obj.matrix_world @ vert.co
            if abs(world.z - target_altitude_scene) <= 1e-9:
                continue
            vert.co = inv_world @ Vector((world.x, world.y, target_altitude_scene))
            aligned += 1

        if bm is not None:
            bmesh.update_edit_mesh(working_obj.data, loop_triangles=False, destructive=False)
        else:
            working_obj.data.update()

        if aligned == 0:
            self.report(
                {"INFO"},
                f"All targeted vertices on '{working_obj.name}' are already at {target_altitude_m:.3f} m in-game altitude.",
            )
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Set {aligned} vertices on '{working_obj.name}' to {target_altitude_m:.3f} m in-game altitude.",
        )
        return {"FINISHED"}


class OBJECT_OT_flightgear_cache_fg_material_library(Operator):
    bl_idname = "object.flightgear_cache_fg_material_library"
    bl_label = "Cache FlightGear Material Library"
    bl_description = "Parse FlightGear materials.xml and create Blender materials for all entries"
    bl_options = {"REGISTER", "UNDO"}

    materials_xml_path: str
    force_refresh_cache: bool
    refresh_existing_materials: bool
    keep_materials_persistent: bool

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "materials_xml_path")
        layout.prop(self, "force_refresh_cache")
        layout.prop(self, "refresh_existing_materials")
        layout.prop(self, "keep_materials_persistent")

    def execute(self, context):
        try:
            texture_root = _texture_root_from_context(context)
            material_map_path = _material_map_path_from_context(context)
            materials_xml_override = _resolved_string_property(getattr(self, "materials_xml_path", ""), "")

            force_refresh_cache = _resolved_bool_property(getattr(self, "force_refresh_cache", False), False)
            refresh_existing_materials = _resolved_bool_property(
                getattr(self, "refresh_existing_materials", False),
                False,
            )
            keep_materials_persistent = _resolved_bool_property(
                getattr(self, "keep_materials_persistent", True),
                True,
            )

            entries = _material_library_entries(
                context,
                materials_xml_override=materials_xml_override,
                use_cache=not force_refresh_cache,
                recursive_fallback=True,
            )
            if not entries:
                materials_root = _resolved_materials_root(context, materials_xml_override)
                self.report(
                    {"ERROR"},
                    "No material entries were found in FlightGear materials definitions"
                    + (f" under {materials_root}." if materials_root else "."),
                )
                return {"CANCELLED"}

            created_count = 0
            refreshed_count = 0
            reused_count = 0
            for material_name in entries:
                existing = bpy.data.materials.get(material_name)
                force_rebuild = refresh_existing_materials and existing is not None
                material = _build_blender_material(
                    material_name,
                    texture_root,
                    material_map_path,
                    textured=True,
                    force_rebuild=force_rebuild,
                )

                if keep_materials_persistent:
                    material.use_fake_user = True

                material["fg_btg_material_library_cached"] = True

                if existing is None:
                    created_count += 1
                elif force_rebuild:
                    refreshed_count += 1
                else:
                    reused_count += 1

            self.report(
                {"INFO"},
                (
                    f"FG material library ready ({len(entries)} entries): "
                    f"{created_count} created, {refreshed_count} refreshed, {reused_count} reused."
                ),
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to cache FlightGear materials: {exc}")
            return {"CANCELLED"}


class OBJECT_OT_flightgear_add_fg_material_from_library(Operator):
    bl_idname = "object.flightgear_add_fg_material_from_library"
    bl_label = "Add FlightGear Material"
    bl_description = "Search FlightGear materials.xml and add one material to the current Blender file"
    bl_options = {"REGISTER", "UNDO"}

    material_name: str
    keep_material_persistent: bool

    def invoke(self, context, _event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            material_name = _resolved_string_property(getattr(self, "material_name", ""), "").strip()
            if not material_name:
                self.report({"ERROR"}, "No FlightGear material selected.")
                return {"CANCELLED"}

            texture_root = _texture_root_from_context(context)
            material_map_path = _material_map_path_from_context(context)
            keep_persistent = _resolved_bool_property(getattr(self, "keep_material_persistent", True), True)

            existing = bpy.data.materials.get(material_name)
            material = _build_blender_material(
                material_name,
                texture_root,
                material_map_path,
                textured=True,
                force_rebuild=False,
            )
            if keep_persistent:
                material.use_fake_user = True
            material["fg_btg_material_library_cached"] = True

            created_or_reused = "created" if existing is None else "reused"
            self.report({"INFO"}, f"FlightGear material '{material_name}' {created_or_reused}.")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to add FlightGear material: {exc}")
            return {"CANCELLED"}


class OBJECT_OT_flightgear_clear_cached_material_library(Operator):
    bl_idname = "object.flightgear_clear_cached_material_library"
    bl_label = "Clear Cached FlightGear Materials"
    bl_description = "Remove or unpin materials created by the FlightGear material-library cache tools"
    bl_options = {"REGISTER", "UNDO"}

    remove_used_materials: bool
    clear_fake_user_only: bool

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "remove_used_materials")
        layout.prop(self, "clear_fake_user_only")

    def execute(self, _context):
        try:
            remove_used = _resolved_bool_property(getattr(self, "remove_used_materials", False), False)
            clear_fake_user_only = _resolved_bool_property(getattr(self, "clear_fake_user_only", False), False)

            cached_materials = [
                material
                for material in bpy.data.materials
                if bool(material.get("fg_btg_material_library_cached", False))
            ]
            if not cached_materials:
                self.report({"INFO"}, "No cached FlightGear materials were found.")
                return {"CANCELLED"}

            removed = 0
            skipped_in_use = 0
            fake_user_cleared = 0

            for material in list(cached_materials):
                real_users = _material_real_user_count(material)
                if clear_fake_user_only:
                    if material.use_fake_user:
                        material.use_fake_user = False
                        fake_user_cleared += 1
                    continue

                if real_users > 0 and not remove_used:
                    skipped_in_use += 1
                    continue

                bpy.data.materials.remove(material)
                removed += 1

            self.report(
                {"INFO"},
                (
                    f"Cached FG materials cleanup: {removed} removed, "
                    f"{fake_user_cleared} fake-users cleared, {skipped_in_use} in-use skipped."
                ),
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to clear cached FlightGear materials: {exc}")
            return {"CANCELLED"}


class VIEW3D_PT_flightgear_btg_tools(Panel):
    bl_label = "FlightGear BTG"
    bl_idname = "VIEW3D_PT_flightgear_btg_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FlightGear"

    def draw(self, context):
        layout = self.layout
        anchor_obj, error_message = _resolve_anchor_tile_object(context)

        available_material_count = 0
        cached_material_count = 0
        if bpy is not None:
            try:
                available_material_count = len(_material_library_entries(context, use_cache=True, recursive_fallback=True))
            except Exception:
                available_material_count = 0
            cached_material_count = sum(
                1
                for material in bpy.data.materials
                if bool(material.get("fg_btg_material_library_cached", False))
            )

        if anchor_obj is None:
            layout.label(text="Select an imported BTG tile.")
            if error_message:
                layout.label(text=error_message)
            return

        source_path = str(anchor_obj.get("fg_btg_source", ""))
        basename = os.path.basename(source_path) if source_path else anchor_obj.name
        adjacent_objects = _adjacent_reference_objects_for_anchor(context.scene, anchor_obj)
        unique_adjacent_tiles = {
            os.path.abspath(str(obj.get("fg_btg_source", "")))
            for obj in adjacent_objects
            if not obj.get("fg_btg_is_point_group") and str(obj.get("fg_btg_source", ""))
        }
        adjacent_meshes = _adjacent_reference_mesh_objects_for_anchor(context.scene, anchor_obj)
        display_label, front_label, select_label = _adjacent_display_summary(adjacent_meshes)

        layout.label(text=f"Active Tile: {basename}")

        tile_box, tile_open = _draw_collapsible_section(
            layout,
            context.scene,
            "fg_btg_ui_tile_metadata_expanded",
            "Tile Metadata",
        )
        if tile_open:
            tile_box.operator(OBJECT_OT_flightgear_retarget_tile.bl_idname, text="Retarget Tile")
            tile_index, _center_error_m, tile_status_label = _tile_metadata_status(anchor_obj)
            if tile_index is None:
                tile_box.label(text="Source Tile Index: Unknown")
            else:
                tile_box.label(text=f"Source Tile Index: {tile_index}")
            tile_box.label(text=tile_status_label)

        adjacent_box, adjacent_open = _draw_collapsible_section(
            layout,
            context.scene,
            "fg_btg_ui_adjacent_tiles_expanded",
            "Adjacent Tiles",
        )
        if adjacent_open:
            adjacent_box.label(text=f"Adjacent Tiles Loaded: {len(unique_adjacent_tiles)}")
            adjacent_box.label(text=f"Adjacent Display: {display_label}")
            adjacent_box.label(text=f"Adjacent In Front: {front_label}")
            adjacent_box.label(text=f"Adjacent Selection: {select_label}")

            column = adjacent_box.column(align=True)
            column.operator(OBJECT_OT_flightgear_load_adjacent_tiles.bl_idname, text="Load Adjacent Tiles")
            load_with_placeholder_op = column.operator(
                OBJECT_OT_flightgear_load_adjacent_tiles.bl_idname,
                text="Load + Ocean Placeholders",
            )
            load_with_placeholder_op.create_ocean_placeholders_for_missing_adjacent = True
            column.operator(OBJECT_OT_flightgear_clear_adjacent_tiles.bl_idname, text="Remove Adjacent Tiles")

            if _tile_index_from_path(source_path) is None:
                adjacent_box.separator()
                adjacent_box.label(text="Adjacent lookup requires a numeric")
                adjacent_box.label(text="FlightGear bucket file name.")

        conform_box, conform_open = _draw_collapsible_section(
            layout,
            context.scene,
            "fg_btg_ui_tile_pair_conform_expanded",
            "Tile Pair Conform",
        )
        if conform_open:
            conform_box.prop_search(context.scene, "fg_btg_working_mesh_name", context.scene, "objects", text="Working Mesh")
            conform_box.prop_search(context.scene, "fg_btg_reference_mesh_name", context.scene, "objects", text="Reference Mesh")

            row = conform_box.row(align=True)
            row.operator(OBJECT_OT_flightgear_set_working_mesh_from_active.bl_idname, text="Set to Working Mesh")
            row.operator(OBJECT_OT_flightgear_set_reference_mesh_from_selection.bl_idname, text="Set to Reference Mesh")

            conform_box.operator(
                OBJECT_OT_flightgear_align_objects_from_metadata.bl_idname,
                text="Align Objects",
            )

            conform_op = conform_box.operator(OBJECT_OT_flightgear_conform_seam_vertices.bl_idname, text="Conform Seam Vertices")
            conform_op.working_tile_name = _scene_working_mesh_name(context.scene)
            conform_op.reference_tile_name = _scene_reference_mesh_name(context.scene)
            conform_op.target_vertices = "SELECTED" if getattr(context, "mode", "") == "EDIT_MESH" else "BOUNDARY"

            altitude_op = conform_box.operator(
                OBJECT_OT_flightgear_set_vertices_in_game_altitude.bl_idname,
                text="Set Vertices at a Specific In-Game Altitude",
            )
            altitude_op.working_tile_name = _scene_working_mesh_name(context.scene)
            altitude_op.target_vertices = "SELECTED" if getattr(context, "mode", "") == "EDIT_MESH" else "BOUNDARY"
            altitude_op.altitude_m = 0.0

        display_box, display_open = _draw_collapsible_section(
            layout,
            context.scene,
            "fg_btg_ui_display_helpers_expanded",
            "Display Helpers",
        )
        if display_open:
            display_box.operator(OBJECT_OT_flightgear_adjacent_edit_preset.bl_idname, text="Seam Edit Preset")

            row = display_box.row(align=True)
            wire_op = row.operator(OBJECT_OT_flightgear_adjacent_display_mode.bl_idname, text="Wire")
            wire_op.display_mode = "WIRE"
            solid_op = row.operator(OBJECT_OT_flightgear_adjacent_display_mode.bl_idname, text="Solid")
            solid_op.display_mode = "TEXTURED"

            row = display_box.row(align=True)
            front_on_op = row.operator(OBJECT_OT_flightgear_adjacent_show_in_front.bl_idname, text="In Front On")
            front_on_op.show_in_front = True
            front_off_op = row.operator(OBJECT_OT_flightgear_adjacent_show_in_front.bl_idname, text="In Front Off")
            front_off_op.show_in_front = False

            row = display_box.row(align=True)
            unlock_op = row.operator(OBJECT_OT_flightgear_adjacent_selectable.bl_idname, text="Selectable")
            unlock_op.selectable = True
            lock_op = row.operator(OBJECT_OT_flightgear_adjacent_selectable.bl_idname, text="Lock Selection")
            lock_op.selectable = False

        material_box, material_open = _draw_collapsible_section(
            layout,
            context.scene,
            "fg_btg_ui_material_library_expanded",
            "Material Library",
        )
        if material_open:
            material_box.label(text=f"Cached: {cached_material_count} | Available: {available_material_count}")
            material_box.operator(
                OBJECT_OT_flightgear_cache_fg_material_library.bl_idname,
                text="Cache FlightGear Materials",
            )
            material_box.operator(
                OBJECT_OT_flightgear_add_fg_material_from_library.bl_idname,
                text="Add One Material (Search)",
            )
            refresh_op = material_box.operator(
                OBJECT_OT_flightgear_cache_fg_material_library.bl_idname,
                text="Refresh Cached Materials",
            )
            refresh_op.force_refresh_cache = True
            refresh_op.refresh_existing_materials = True
            material_box.operator(
                OBJECT_OT_flightgear_clear_cached_material_library.bl_idname,
                text="Clear Cached Materials",
            )


apply_class_properties(globals())
menu_func_import, menu_func_export, menu_func_object = make_menu_functions(globals())
classes = build_classes(globals())


def register():
    if bpy is None:
        raise RuntimeError("This add-on can only be registered inside Blender")

    register_addon(
        bpy,
        classes,
        FlightGearMaterialSettings,
        menu_func_import,
        menu_func_export,
        menu_func_object,
        PointerProperty,
        StringProperty,
    )


def unregister():
    unregister_addon(
        bpy,
        classes,
        menu_func_import,
        menu_func_export,
        menu_func_object,
    )


if __name__ == "__main__":
    register()
