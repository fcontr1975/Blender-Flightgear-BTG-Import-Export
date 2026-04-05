import gzip
import struct
import time

try:
    from .fg_btg_geo import _encode_normal_component
except ImportError:
    from fg_btg_geo import _encode_normal_component

BTG_MAGIC = 0x5347


class BTGData:
    def __init__(self):
        self.version = 10
        self.creation_time = 0
        self.center = (0.0, 0.0, 0.0)
        self.radius = 0.0
        self.vertices = []
        self.faces = []
        self.texcoords = []
        self.face_texcoords = []
        self.face_materials = []
        self.point_groups = []


def _header_and_count_sizes(version):
    if version >= 10:
        return 12, 4
    return 10, 2


def _geometry_index_size(version):
    return 4 if version >= 10 else 2


def _parse_geometry_entries(raw, index_types, object_type, version):
    if index_types is None:
        index_types = 0x01 if object_type == 9 else 0x09

    stride_indices = 0
    for bit in range(4):
        if index_types & (1 << bit):
            stride_indices += 1

    if stride_indices == 0:
        return []

    index_size = _geometry_index_size(version)
    stride = stride_indices * index_size
    tuple_count = len(raw) // stride
    entries = []

    for i in range(tuple_count):
        base = i * stride
        cursor = base
        entry = {"v": None, "t": None}
        for bit in range(4):
            if index_types & (1 << bit):
                if index_size == 4:
                    idx = struct.unpack_from("<I", raw, cursor)[0]
                else:
                    idx = struct.unpack_from("<H", raw, cursor)[0]
                cursor += index_size
                if bit == 0:
                    entry["v"] = idx
                elif bit == 3:
                    entry["t"] = idx
        if entry["v"] is not None:
            entries.append(entry)

    return entries


def _entries_to_faces(entries, object_type):
    faces = []
    uv_faces = []

    if object_type == 10:
        for i in range(0, len(entries) - 2, 3):
            tri = (entries[i], entries[i + 1], entries[i + 2])
            vi = (tri[0]["v"], tri[1]["v"], tri[2]["v"])
            ti = (tri[0]["t"], tri[1]["t"], tri[2]["t"])
            if len(set(vi)) == 3:
                faces.append(vi)
                uv_faces.append(ti)

    elif object_type == 11:
        for i in range(0, len(entries) - 2):
            if i % 2 == 0:
                tri = (entries[i], entries[i + 1], entries[i + 2])
            else:
                tri = (entries[i + 1], entries[i], entries[i + 2])

            vi = (tri[0]["v"], tri[1]["v"], tri[2]["v"])
            ti = (tri[0]["t"], tri[1]["t"], tri[2]["t"])
            if len(set(vi)) == 3:
                faces.append(vi)
                uv_faces.append(ti)

    elif object_type == 12 and len(entries) >= 3:
        anchor = entries[0]
        for i in range(1, len(entries) - 1):
            tri = (anchor, entries[i], entries[i + 1])
            vi = (tri[0]["v"], tri[1]["v"], tri[2]["v"])
            ti = (tri[0]["t"], tri[1]["t"], tri[2]["t"])
            if len(set(vi)) == 3:
                faces.append(vi)
                uv_faces.append(ti)

    return faces, uv_faces


def _append_faces_for_geometry(object_type, entries_per_element, faces, face_texcoords):
    if object_type == 10:
        flattened = []
        for element_entries in entries_per_element:
            flattened.extend(element_entries)
        new_faces, new_uv_faces = _entries_to_faces(flattened, object_type)
        faces.extend(new_faces)
        face_texcoords.extend(new_uv_faces)
    else:
        for element_entries in entries_per_element:
            new_faces, new_uv_faces = _entries_to_faces(element_entries, object_type)
            faces.extend(new_faces)
            face_texcoords.extend(new_uv_faces)


def parse_btg(filepath):
    data = BTGData()

    with open(filepath, "rb") as f:
        raw = f.read()

    if len(raw) < 10:
        raise ValueError("BTG file too short to contain a valid header")

    version, magic = struct.unpack_from("<HH", raw, 0)
    if magic != BTG_MAGIC:
        raise ValueError("Invalid BTG magic number")

    header_size, count_size = _header_and_count_sizes(version)
    if len(raw) < header_size:
        raise ValueError("BTG file too short to contain a complete header")

    creation_time = struct.unpack_from("<I", raw, 4)[0]
    if count_size == 4:
        num_objects = struct.unpack_from("<I", raw, 8)[0]
    else:
        num_objects = struct.unpack_from("<H", raw, 8)[0]

    data.version = version
    data.creation_time = creation_time

    offset = header_size

    for _ in range(num_objects):
        object_header_size = 9 if version >= 10 else 5
        if offset + object_header_size > len(raw):
            break

        object_type = struct.unpack_from("<B", raw, offset)[0]
        offset += 1
        if version >= 10:
            num_props, num_elems = struct.unpack_from("<II", raw, offset)
            offset += 8
        else:
            num_props, num_elems = struct.unpack_from("<HH", raw, offset)
            offset += 4

        index_types = None
        material = ""
        entries_per_element = []

        for _prop in range(num_props):
            if offset + 5 > len(raw):
                break
            prop_type, prop_size = struct.unpack_from("<BI", raw, offset)
            offset += 5
            prop_raw = raw[offset: offset + prop_size]
            offset += prop_size

            if prop_type == 0:
                material = prop_raw.decode("utf-8", errors="replace")
            elif prop_type == 1 and prop_size >= 1:
                index_types = prop_raw[0]

        for _elem in range(num_elems):
            if offset + 4 > len(raw):
                break
            elem_size = struct.unpack_from("<I", raw, offset)[0]
            offset += 4
            elem_raw = raw[offset: offset + elem_size]
            offset += elem_size

            if object_type == 0 and elem_size >= 28:
                cx, cy, cz, radius = struct.unpack_from("<dddf", elem_raw, 0)
                data.center = (cx, cy, cz)
                data.radius = radius
            elif object_type == 1:
                vert_count = elem_size // 12
                for i in range(vert_count):
                    vx, vy, vz = struct.unpack_from("<fff", elem_raw, i * 12)
                    data.vertices.append((vx, vy, vz))
            elif object_type == 3:
                uv_count = elem_size // 8
                for i in range(uv_count):
                    u, v = struct.unpack_from("<ff", elem_raw, i * 8)
                    data.texcoords.append((u, v))
            elif object_type in (9, 10, 11, 12):
                entries = _parse_geometry_entries(elem_raw, index_types, object_type, version)
                entries_per_element.append(entries)

        if object_type in (10, 11, 12):
            before_count = len(data.faces)
            _append_faces_for_geometry(
                object_type,
                entries_per_element,
                data.faces,
                data.face_texcoords,
            )
            new_count = len(data.faces) - before_count
            if new_count > 0:
                data.face_materials.extend([material] * new_count)
        elif object_type == 9:
            flat_entries = []
            for element_entries in entries_per_element:
                flat_entries.extend(element_entries)
            point_indices = [entry["v"] for entry in flat_entries if entry.get("v") is not None]
            if point_indices:
                data.point_groups.append(
                    {
                        "material": material,
                        "indices": point_indices,
                    }
                )

    max_idx = len(data.vertices) - 1
    valid_faces = []
    valid_uv_faces = []
    valid_materials = []
    max_tex_idx = len(data.texcoords) - 1

    for i, (a, b, c) in enumerate(data.faces):
        if a <= max_idx and b <= max_idx and c <= max_idx:
            valid_faces.append((a, b, c))
            if i < len(data.face_texcoords):
                ta, tb, tc = data.face_texcoords[i]
                if (
                    ta is not None
                    and tb is not None
                    and tc is not None
                    and ta <= max_tex_idx
                    and tb <= max_tex_idx
                    and tc <= max_tex_idx
                ):
                    valid_uv_faces.append((ta, tb, tc))
                else:
                    valid_uv_faces.append((None, None, None))
            else:
                valid_uv_faces.append((None, None, None))

            if i < len(data.face_materials):
                valid_materials.append(data.face_materials[i])
            else:
                valid_materials.append("")

    data.faces = valid_faces
    data.face_texcoords = valid_uv_faces
    data.face_materials = valid_materials

    valid_point_groups = []
    for group in data.point_groups:
        raw_indices = group.get("indices", [])
        valid_indices = [idx for idx in raw_indices if 0 <= idx <= max_idx]
        if valid_indices:
            valid_point_groups.append(
                {
                    "material": group.get("material", ""),
                    "indices": valid_indices,
                }
            )
    data.point_groups = valid_point_groups

    return data


def _pack_object_versioned(version, object_type, properties, elements):
    blob = bytearray()
    if version >= 10:
        blob.extend(struct.pack("<BII", object_type, len(properties), len(elements)))
    else:
        blob.extend(struct.pack("<BHH", object_type, len(properties), len(elements)))

    for prop_type, prop_data in properties:
        blob.extend(struct.pack("<BI", prop_type, len(prop_data)))
        blob.extend(prop_data)

    for elem_data in elements:
        blob.extend(struct.pack("<I", len(elem_data)))
        blob.extend(elem_data)

    return bytes(blob)


def _max_group_size_by_material(face_materials):
    if not face_materials:
        return 0

    grouped_counts = {}
    for material_name in face_materials:
        key = material_name or ""
        grouped_counts[key] = grouped_counts.get(key, 0) + 1
    return max(grouped_counts.values())


def _preferred_btg_version(vertices, normals, texcoords, face_materials, requested_version):
    if requested_version < 10:
        return requested_version

    if (
        len(vertices) < 0xFFFF
        and len(normals) < 0xFFFF
        and len(texcoords) < 0xFFFF
        and _max_group_size_by_material(face_materials) < 0x7FFF
    ):
        return 7

    return requested_version


def write_btg(
    filepath,
    vertices_world,
    normals,
    faces,
    face_uv_indices=None,
    texcoords=None,
    face_materials=None,
    point_groups=None,
    center=(0.0, 0.0, 0.0),
    version=10,
):
    face_uv_indices = face_uv_indices or []
    texcoords = texcoords or []
    face_materials = face_materials or []
    point_groups = point_groups or []
    normals = normals or []
    version = _preferred_btg_version(vertices_world, normals, texcoords, face_materials, version)

    cx, cy, cz = center

    vertices_rel = []
    max_dist_sq = 0.0

    for vx, vy, vz in vertices_world:
        rx = vx - cx
        ry = vy - cy
        rz = vz - cz
        vertices_rel.append((rx, ry, rz))

        dx = vx - cx
        dy = vy - cy
        dz = vz - cz
        dist_sq = dx * dx + dy * dy + dz * dz
        if dist_sq > max_dist_sq:
            max_dist_sq = dist_sq

    radius = max_dist_sq ** 0.5

    objects = []

    bs_elem = struct.pack("<dddf", cx, cy, cz, radius)
    objects.append(_pack_object_versioned(version, 0, [], [bs_elem]))

    vertex_elem = bytearray()
    for vx, vy, vz in vertices_rel:
        vertex_elem.extend(struct.pack("<fff", vx, vy, vz))
    objects.append(_pack_object_versioned(version, 1, [], [bytes(vertex_elem)]))

    objects.append(_pack_object_versioned(version, 4, [], [b""]))

    normal_elem = bytearray()
    for nx, ny, nz in normals:
        normal_elem.extend(
            bytes(
                (
                    _encode_normal_component(nx),
                    _encode_normal_component(ny),
                    _encode_normal_component(nz),
                )
            )
        )
    objects.append(_pack_object_versioned(version, 2, [], [bytes(normal_elem)]))

    tex_elem = bytearray()
    for u, v in texcoords:
        tex_elem.extend(struct.pack("<ff", float(u), float(v)))
    objects.append(_pack_object_versioned(version, 3, [], [bytes(tex_elem)]))

    grouped = {}
    for i, face in enumerate(faces):
        material = face_materials[i] if i < len(face_materials) else ""
        uv = face_uv_indices[i] if i < len(face_uv_indices) else (None, None, None)
        use_uv = bool(texcoords) and all(v is not None for v in uv)
        use_normals = bool(normals)
        key = (material, use_uv, use_normals)
        grouped.setdefault(key, []).append((face, uv))

    for (material, use_uv, use_normals), grouped_faces in grouped.items():
        index_types = 0x01
        if use_normals:
            index_types |= 0x02
        if use_uv:
            index_types |= 0x08
        tri_properties = [(1, bytes([index_types]))]
        if material:
            tri_properties.insert(0, (0, material.encode("utf-8", errors="replace")))

        tri_elements = []
        for (a, b, c), (ta, tb, tc) in grouped_faces:
            if use_uv:
                if version >= 10:
                    if use_normals:
                        tri_elements.append(
                            struct.pack("<IIIIIIIII", a, a, ta, b, b, tb, c, c, tc)
                        )
                    else:
                        tri_elements.append(
                            struct.pack("<IIIIII", a, ta, b, tb, c, tc)
                        )
                else:
                    if use_normals:
                        tri_elements.append(
                            struct.pack("<HHHHHHHHH", a, a, ta, b, b, tb, c, c, tc)
                        )
                    else:
                        tri_elements.append(
                            struct.pack("<HHHHHH", a, ta, b, tb, c, tc)
                        )
            else:
                if version >= 10:
                    if use_normals:
                        tri_elements.append(struct.pack("<IIIIII", a, a, b, b, c, c))
                    else:
                        tri_elements.append(struct.pack("<III", a, b, c))
                else:
                    if use_normals:
                        tri_elements.append(struct.pack("<HHHHHH", a, a, b, b, c, c))
                    else:
                        tri_elements.append(struct.pack("<HHH", a, b, c))

        objects.append(_pack_object_versioned(version, 10, tri_properties, tri_elements))

    grouped_points = {}
    for point_group in point_groups:
        material = point_group.get("material", "") or ""
        indices = point_group.get("indices", [])
        if not indices:
            continue
        grouped_points.setdefault(material, []).extend(indices)

    for material, raw_indices in grouped_points.items():
        seen = set()
        point_indices = []
        for idx in raw_indices:
            if idx in seen:
                continue
            seen.add(idx)
            point_indices.append(idx)
        if not point_indices:
            continue

        idx_mask = 0x01
        pt_properties = [(1, bytes([idx_mask]))]
        if material:
            pt_properties.insert(0, (0, material.encode("utf-8", errors="replace")))

        if version >= 10:
            pt_element = struct.pack("<" + "I" * len(point_indices), *point_indices)
        else:
            pt_element = struct.pack("<" + "H" * len(point_indices), *point_indices)

        objects.append(_pack_object_versioned(version, 9, pt_properties, [pt_element]))

    if version >= 10:
        header = struct.pack("<HHII", version, BTG_MAGIC, int(time.time()), len(objects))
    else:
        header = struct.pack("<HHIH", version, BTG_MAGIC, int(time.time()), len(objects))

    with open(filepath, "wb") as f:
        f.write(header)
        for obj_blob in objects:
            f.write(obj_blob)


def _decompress_btg_gz_to_folder(gz_path):
    if not gz_path.lower().endswith(".gz"):
        return gz_path

    out_path = gz_path[:-3]
    with gzip.open(gz_path, "rb") as src, open(out_path, "wb") as dst:
        dst.write(src.read())
    return out_path
