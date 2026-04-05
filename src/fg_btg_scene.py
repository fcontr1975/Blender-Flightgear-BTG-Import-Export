import math
import os

try:
    from .fg_btg_geo import (
        _bucket_base_path,
        _bucket_from_index,
        _ecef_to_enu_matrix,
        _normalize3,
        _point_group_tile_index_from_name,
        _rotate3_inv,
        _tile_index_from_path,
    )
    from .fg_btg_materials import (
        _material_export_name,
        _material_uses_dds,
        _material_wrap_flags,
        _material_wrap_settings_map,
    )
except ImportError:
    from fg_btg_geo import (
        _bucket_base_path,
        _bucket_from_index,
        _ecef_to_enu_matrix,
        _normalize3,
        _point_group_tile_index_from_name,
        _rotate3_inv,
        _tile_index_from_path,
    )
    from fg_btg_materials import (
        _material_export_name,
        _material_uses_dds,
        _material_wrap_flags,
        _material_wrap_settings_map,
    )

IMPORT_SCALE = 0.01
EXPORT_SCALE = 100.0


def _is_point_group_object(obj):
    if bool(obj.get("fg_btg_is_point_group")):
        return True
    return _point_group_tile_index_from_name(getattr(obj, "name", "")) is not None


def _point_group_vertex_count(point_groups):
    total = 0
    for group in point_groups:
        total += len(group.get("indices", []))
    return total


def _btg_output_basename(filepath):
    basename = os.path.basename(filepath)
    if basename.lower().endswith(".gz"):
        basename = basename[:-3]
    stem, _ext = os.path.splitext(basename)
    return stem


def _extract_export_mesh_data(
    context,
    export_selected=True,
    coordinate_scale=EXPORT_SCALE,
    apply_enu_inverse=False,
    preserve_btg_local_frame=False,
    reverse_dds_view_flip=False,
    texture_root=None,
    material_map_path="",
    materials_xml_override="",
):
    depsgraph = context.evaluated_depsgraph_get()

    if export_selected:
        objects = list(context.selected_objects)
        seen_ptrs = {obj.as_pointer() for obj in objects}
        pending = list(objects)
        while pending:
            current = pending.pop()
            for child in getattr(current, "children", []):
                if not child.get("fg_btg_is_point_group"):
                    continue
                ptr = child.as_pointer()
                if ptr in seen_ptrs:
                    continue
                seen_ptrs.add(ptr)
                objects.append(child)
                pending.append(child)

        selected_tile_ids = set()
        for obj in objects:
            if obj.type != "MESH":
                continue
            source_path = obj.get("fg_btg_source")
            if isinstance(source_path, str) and source_path:
                selected_tile_ids.add(_btg_output_basename(source_path))

        if selected_tile_ids:
            for scene_obj in context.scene.objects:
                if scene_obj.type != "MESH":
                    continue
                ptr = scene_obj.as_pointer()
                if ptr in seen_ptrs:
                    continue
                point_tile_id = _point_group_tile_index_from_name(scene_obj.name)
                if point_tile_id and point_tile_id in selected_tile_ids:
                    seen_ptrs.add(ptr)
                    objects.append(scene_obj)
    else:
        objects = context.scene.objects
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]

    source_center_map = {}
    source_frame_map = {}
    for scene_obj in context.scene.objects:
        if scene_obj.type != "MESH":
            continue
        if scene_obj.get("fg_btg_is_adjacent_reference"):
            continue
        source_path = scene_obj.get("fg_btg_source")
        if not isinstance(source_path, str) or not source_path:
            continue
        key = os.path.abspath(source_path)
        source_center_map[key] = (
            float(scene_obj.get("fg_btg_center_x", 0.0)),
            float(scene_obj.get("fg_btg_center_y", 0.0)),
            float(scene_obj.get("fg_btg_center_z", 0.0)),
        )
        tile_id = _btg_output_basename(source_path)
        if tile_id not in source_frame_map:
            source_frame_map[tile_id] = {
                "center": source_center_map[key],
                "import_scale": float(scene_obj.get("fg_btg_import_scale", IMPORT_SCALE)),
                "enu_applied": bool(scene_obj.get("fg_btg_enu_applied")),
                "z_offset": float(scene_obj.get("fg_btg_z_offset", 0.0)),
            }

    vertices = []
    normals = []
    faces = []
    texcoords = []
    face_uv_indices = []
    face_materials = []
    point_groups = []
    texcoord_index = {}
    texcoord_records = []
    wrap_settings_map = _material_wrap_settings_map(context, materials_xml_override)

    for obj in mesh_objects:
        obj_enu_rot = None
        obj_center = (
            float(obj.get("fg_btg_center_x", 0.0)),
            float(obj.get("fg_btg_center_y", 0.0)),
            float(obj.get("fg_btg_center_z", 0.0)),
        )
        is_exportable_reference = bool(obj.get("fg_btg_exportable_reference"))
        center_offset_scene = None
        obj_import_scale = float(obj.get("fg_btg_import_scale", IMPORT_SCALE))
        obj_z_offset = float(obj.get("fg_btg_z_offset", 0.0))
        obj_enu_applied = bool(obj.get("fg_btg_enu_applied"))
        is_point_group = _is_point_group_object(obj)

        if is_point_group and not obj_enu_applied:
            point_tile_id = _point_group_tile_index_from_name(getattr(obj, "name", ""))
            inherited_frame = source_frame_map.get(point_tile_id)
            if inherited_frame is not None:
                obj_center = inherited_frame["center"]
                obj_import_scale = inherited_frame["import_scale"]
                obj_enu_applied = inherited_frame["enu_applied"]
                obj_z_offset = inherited_frame["z_offset"]

        if apply_enu_inverse and obj_enu_applied:
            if is_exportable_reference:
                ax = float(obj.get("fg_btg_anchor_center_x", 0.0))
                ay = float(obj.get("fg_btg_anchor_center_y", 0.0))
                az = float(obj.get("fg_btg_anchor_center_z", 0.0))
                if not (ax or ay or az):
                    anchor_source = obj.get("fg_btg_anchor_source")
                    if isinstance(anchor_source, str) and anchor_source:
                        fallback_center = source_center_map.get(os.path.abspath(anchor_source))
                        if fallback_center is not None:
                            ax, ay, az = fallback_center
                if ax or ay or az:
                    obj_enu_rot = _ecef_to_enu_matrix(ax, ay, az)
                    center_offset_ecef = (
                        obj_center[0] - ax,
                        obj_center[1] - ay,
                        obj_center[2] - az,
                    )
                    center_offset_scene = (
                        center_offset_ecef[0] * obj_import_scale,
                        center_offset_ecef[1] * obj_import_scale,
                        center_offset_ecef[2] * obj_import_scale,
                    )
            else:
                cx, cy, cz = obj_center
                if cx or cy or cz:
                    obj_enu_rot = _ecef_to_enu_matrix(cx, cy, cz)

        eval_obj = obj.evaluated_get(depsgraph)
        if is_point_group:
            mesh = obj.data
        else:
            mesh = eval_obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
        if mesh is None:
            continue

        base = len(vertices)
        normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
        use_btg_local_frame = bool(
            preserve_btg_local_frame
            and obj.get("fg_btg_enu_applied")
            and apply_enu_inverse
            and not is_exportable_reference
        )

        for v in mesh.vertices:
            if use_btg_local_frame:
                x, y, z = v.co.x, v.co.y, v.co.z
            else:
                world = obj.matrix_world @ v.co
                x, y, z = world.x, world.y, world.z
            if obj_enu_rot is not None:
                z += obj_z_offset
                x, y, z = _rotate3_inv((x, y, z), obj_enu_rot)
                if center_offset_scene is not None:
                    x -= center_offset_scene[0]
                    y -= center_offset_scene[1]
                    z -= center_offset_scene[2]
            vertices.append((x * coordinate_scale, y * coordinate_scale, z * coordinate_scale))

            if use_btg_local_frame:
                nx, ny, nz = v.normal.x, v.normal.y, v.normal.z
            else:
                world_normal = normal_matrix @ v.normal
                nx, ny, nz = world_normal.x, world_normal.y, world_normal.z
            if obj_enu_rot is not None:
                nx, ny, nz = _rotate3_inv((nx, ny, nz), obj_enu_rot)
            normals.append(_normalize3((nx, ny, nz)))

        uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            a, b, c = tri.vertices
            faces.append((base + a, base + b, base + c))

            material = None
            mat_name = ""
            if tri.material_index < len(mesh.materials) and mesh.materials[tri.material_index] is not None:
                material = mesh.materials[tri.material_index]
                mat_name = _material_export_name(material, texture_root, material_map_path)
            face_materials.append(mat_name)

            if uv_layer is not None:
                tri_uv = []
                flip_v_for_dds = bool(reverse_dds_view_flip and _material_uses_dds(material))
                wrap_u, wrap_v = _material_wrap_flags(material, mat_name, wrap_settings_map)
                for loop_index in tri.loops:
                    uv = uv_layer[loop_index].uv
                    u = float(uv.x)
                    v = float(uv.y)
                    if flip_v_for_dds:
                        v = 1.0 - v
                    key = (u, v, wrap_u, wrap_v)
                    idx = texcoord_index.get(key)
                    if idx is None:
                        idx = len(texcoord_records)
                        texcoord_index[key] = idx
                        texcoord_records.append(key)
                    tri_uv.append(idx)
                face_uv_indices.append((tri_uv[0], tri_uv[1], tri_uv[2]))
            else:
                face_uv_indices.append((None, None, None))

        if is_point_group:
            point_indices = [base + i for i in range(len(mesh.vertices))]
            if point_indices:
                point_material = obj.get("fg_btg_point_material", "") or ""
                if not point_material and mesh.materials and mesh.materials[0] is not None:
                    mat = mesh.materials[0]
                    point_material = mat.get("fg_btg_material_name", mat.name)
                point_groups.append(
                    {
                        "material": point_material or "Default",
                        "indices": point_indices,
                    }
                )

        if not is_point_group:
            eval_obj.to_mesh_clear()

    if texcoord_records:
        wrapped_us = [u for u, _v, wrap_u, _wrap_v in texcoord_records if wrap_u]
        wrapped_vs = [v for _u, v, _wrap_u, wrap_v in texcoord_records if wrap_v]
        shift_u = int(math.floor(-min(wrapped_us))) + 1 if wrapped_us and min(wrapped_us) < 0.0 else 0
        shift_v = int(math.floor(-min(wrapped_vs))) + 1 if wrapped_vs and min(wrapped_vs) < 0.0 else 0
        texcoords = [
            (
                u + shift_u if wrap_u else u,
                v + shift_v if wrap_v else v,
            )
            for u, v, wrap_u, wrap_v in texcoord_records
        ]
    else:
        texcoords = []

    return (
        mesh_objects,
        vertices,
        normals,
        faces,
        texcoords,
        face_uv_indices,
        face_materials,
        point_groups,
    )


def _center_from_objects(objects):
    for obj in objects:
        if "fg_btg_center_x" in obj and "fg_btg_center_y" in obj and "fg_btg_center_z" in obj:
            return (
                float(obj["fg_btg_center_x"]),
                float(obj["fg_btg_center_y"]),
                float(obj["fg_btg_center_z"]),
            )
    return (0.0, 0.0, 0.0)


def _has_mixed_btg_centers(objects, tolerance=0.01):
    centers = []
    for obj in objects:
        if "fg_btg_center_x" in obj and "fg_btg_center_y" in obj and "fg_btg_center_z" in obj:
            centers.append(
                (
                    float(obj["fg_btg_center_x"]),
                    float(obj["fg_btg_center_y"]),
                    float(obj["fg_btg_center_z"]),
                )
            )

    if len(centers) <= 1:
        return False

    base = centers[0]
    for cx, cy, cz in centers[1:]:
        if (
            abs(cx - base[0]) > tolerance
            or abs(cy - base[1]) > tolerance
            or abs(cz - base[2]) > tolerance
        ):
            return True

    return False


def _has_untagged_meshes_for_btg_export(objects):
    has_tagged = False
    has_untagged = False

    for obj in objects:
        if _is_point_group_object(obj):
            continue

        tagged = (
            "fg_btg_center_x" in obj
            and "fg_btg_center_y" in obj
            and "fg_btg_center_z" in obj
        )
        if tagged:
            has_tagged = True
        else:
            has_untagged = True

    return has_tagged and has_untagged


def _has_adjacent_reference_tiles(objects):
    for obj in objects:
        if obj.get("fg_btg_is_adjacent_reference") and not obj.get("fg_btg_exportable_reference"):
            return True
    return False


def _stg_path_for_btg_export(output_path):
    path_value = os.path.abspath(output_path)
    if path_value.lower().endswith(".gz"):
        path_value = path_value[:-3]
    base, _ext = os.path.splitext(path_value)
    return base + ".stg"


def _package_btg_destination_preview(output_path, scenery_package_root, objects):
    if not scenery_package_root:
        return ""

    tile_index = _tile_index_from_path(output_path)
    if tile_index is None:
        source_basename = _source_basename_for_objects(objects)
        if source_basename and source_basename.isdigit():
            tile_index = int(source_basename)
    if tile_index is None:
        return ""

    btg_name = os.path.basename(output_path)
    if not btg_name:
        btg_name = f"{tile_index}.btg.gz"
    elif not btg_name.lower().endswith(".btg") and not btg_name.lower().endswith(".btg.gz"):
        btg_name = f"{tile_index}.btg.gz"

    bucket = _bucket_from_index(tile_index)
    return os.path.join(
        os.path.abspath(scenery_package_root),
        "Terrain",
        _bucket_base_path(bucket),
        btg_name,
    )


def _upsert_stg_object_base(stg_path, btg_object_path):
    object_base_line = f"OBJECT_BASE {btg_object_path}\n"
    status = "created"

    if os.path.isfile(stg_path):
        with open(stg_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        status = "updated"

        object_base_index = None
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2 and parts[0].upper() == "OBJECT_BASE":
                object_base_index = idx
                break

        if object_base_index is not None:
            existing = lines[object_base_index].strip()
            if existing == object_base_line.strip():
                return "unchanged"
            lines[object_base_index] = object_base_line
        else:
            insert_at = 0
            while insert_at < len(lines):
                stripped = lines[insert_at].strip()
                if stripped and not stripped.startswith("#"):
                    break
                insert_at += 1
            lines.insert(insert_at, object_base_line)

        with open(stg_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        return status

    os.makedirs(os.path.dirname(stg_path), exist_ok=True)
    with open(stg_path, "w", encoding="utf-8") as handle:
        handle.write("# Auto-generated by FlightGear BTG Blender add-on\n")
        handle.write(object_base_line)
    return status


def _source_basename_for_objects(objects):
    basenames = set()
    for obj in objects:
        source_path = obj.get("fg_btg_source")
        if isinstance(source_path, str) and source_path:
            basenames.add(_btg_output_basename(source_path))
    if len(basenames) == 1:
        return next(iter(basenames))
    return None


def _max_radius_from_center(vertices, center):
    cx, cy, cz = center
    max_dist_sq = 0.0
    for vx, vy, vz in vertices:
        dx = vx - cx
        dy = vy - cy
        dz = vz - cz
        dist_sq = dx * dx + dy * dy + dz * dz
        if dist_sq > max_dist_sq:
            max_dist_sq = dist_sq
    return math.sqrt(max_dist_sq)


def _suspicious_base_tile_replacement_message(objects, output_path, vertices_abs, faces):
    source_basename = _source_basename_for_objects(objects)
    if not source_basename or _btg_output_basename(output_path) != source_basename:
        return None

    original_face_count = None
    original_radius = None
    for obj in objects:
        if original_face_count is None and "fg_btg_original_face_count" in obj:
            original_face_count = int(obj["fg_btg_original_face_count"])
        if original_radius is None and "fg_btg_original_radius" in obj:
            original_radius = float(obj["fg_btg_original_radius"])

    if original_face_count is None or original_radius is None:
        return None

    exported_face_count = len(faces)
    exported_center = _center_from_objects(objects)
    exported_radius = _max_radius_from_center(vertices_abs, exported_center)

    if original_face_count > 0 and exported_face_count < max(32, int(original_face_count * 0.5)):
        return (
            f"Refusing to overwrite base tile '{source_basename}': exported mesh has only "
            f"{exported_face_count} faces vs original {original_face_count}. "
            "Export to a different BTG name for OBJECT use, or export the full tile."
        )

    if original_radius > 0.0 and exported_radius > original_radius * 1.25:
        return (
            f"Refusing to overwrite base tile '{source_basename}': exported radius "
            f"{exported_radius:.1f}m exceeds original {original_radius:.1f}m. "
            "This usually means the selected geometry is not a safe full-tile replacement."
        )

    return None
