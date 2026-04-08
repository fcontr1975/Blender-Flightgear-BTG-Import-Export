import math
import os
import re

IMPORT_SCALE = 0.01
SG_BUCKET_SPAN = 0.125
SG_HALF_BUCKET_SPAN = 0.5 * SG_BUCKET_SPAN
SG_EPSILON = 1e-7
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3


def _normalize_periodic(min_value, max_value, value):
    period = max_value - min_value
    while value < min_value:
        value += period
    while value >= max_value:
        value -= period
    return value


def _floor_with_epsilon(value):
    return int(math.floor(value + SG_EPSILON))


def _bucket_span(latitude):
    if latitude >= 89.0:
        return 12.0
    if latitude >= 86.0:
        return 4.0
    if latitude >= 83.0:
        return 2.0
    if latitude >= 76.0:
        return 1.0
    if latitude >= 62.0:
        return 0.5
    if latitude >= 22.0:
        return 0.25
    if latitude >= -22.0:
        return 0.125
    if latitude >= -62.0:
        return 0.25
    if latitude >= -76.0:
        return 0.5
    if latitude >= -83.0:
        return 1.0
    if latitude >= -86.0:
        return 2.0
    if latitude >= -89.0:
        return 4.0
    return 12.0


def _bucket_from_index(tile_index):
    index = int(tile_index)
    lon = (index >> 14) - 180
    lat = ((index >> 6) & 0xFF) - 90
    y = (index >> 3) & 0x7
    x = index & 0x7
    return {"lon": lon, "lat": lat, "x": x, "y": y}


def _bucket_center_lat(bucket):
    return bucket["lat"] + bucket["y"] / 8.0 + SG_HALF_BUCKET_SPAN


def _bucket_center_lon(bucket):
    span = _bucket_span(_bucket_center_lat(bucket))
    if span >= 1.0:
        return bucket["lon"] + span / 2.0
    return bucket["lon"] + bucket["x"] * span + span / 2.0


def _bucket_center_lon_lat(bucket):
    return (_bucket_center_lon(bucket), _bucket_center_lat(bucket))


def _bucket_corner_lon_lat(bucket):
    center_lon, center_lat = _bucket_center_lon_lat(bucket)
    half_width = _bucket_span(center_lat) * 0.5
    half_height = SG_BUCKET_SPAN * 0.5
    return [
        (center_lon - half_width, center_lat - half_height),
        (center_lon + half_width, center_lat - half_height),
        (center_lon + half_width, center_lat + half_height),
        (center_lon - half_width, center_lat + half_height),
    ]


def _bucket_from_lon_lat(dlon, dlat):
    dlon = _normalize_periodic(-180.0, 180.0, dlon)
    dlat = max(-90.0, min(90.0, dlat))

    span = _bucket_span(dlat)
    lon = _floor_with_epsilon(dlon)
    if span <= 1.0:
        x = _floor_with_epsilon((dlon - lon) / span)
    else:
        lon = int(math.floor(lon / span) * span)
        x = 0

    lat = _floor_with_epsilon(dlat)
    if lat == 90:
        lat = 89
        y = 7
    else:
        y = _floor_with_epsilon((dlat - lat) * 8.0)

    return {"lon": lon, "lat": lat, "x": x, "y": y}


def _bucket_index(bucket):
    return ((bucket["lon"] + 180) << 14) + ((bucket["lat"] + 90) << 6) + (bucket["y"] << 3) + bucket["x"]


def _bucket_sibling(bucket, dx, dy):
    center_lat = _bucket_center_lat(bucket) + dy * SG_BUCKET_SPAN
    if center_lat < -90.0 or center_lat > 90.0:
        return None

    center_lon = _bucket_center_lon(bucket) + dx * _bucket_span(center_lat)
    center_lon = _normalize_periodic(-180.0, 180.0, center_lon)
    return _bucket_from_lon_lat(center_lon, center_lat)


def _bucket_dir_component(lon_deg, lat_deg):
    hem = "e" if lon_deg >= 0 else "w"
    pole = "n" if lat_deg >= 0 else "s"
    return f"{hem}{abs(int(lon_deg)):03d}{pole}{abs(int(lat_deg)):02d}"


def _bucket_base_path(bucket):
    top_lon = (bucket["lon"] // 10) * 10
    top_lat = (bucket["lat"] // 10) * 10
    return os.path.join(
        _bucket_dir_component(top_lon, top_lat),
        _bucket_dir_component(bucket["lon"], bucket["lat"]),
    )


def _tile_index_from_path(path_value):
    basename = os.path.basename(path_value)
    if basename.lower().endswith(".gz"):
        basename = basename[:-3]
    stem, _ext = os.path.splitext(basename)
    if not stem.isdigit():
        return None
    return int(stem)


def _point_group_owner_label_from_name(name):
    if not isinstance(name, str):
        return None
    match = re.match(r"^(.+)_lights(?:_.+)?$", name)
    if match:
        return match.group(1)
    return None


def _point_group_tile_index_from_name(name):
    owner_label = _point_group_owner_label_from_name(name)
    if owner_label and owner_label.isdigit():
        return owner_label
    return None


def _adjacent_bucket_indices(tile_index):
    source_bucket = _bucket_from_index(tile_index)
    neighbor_indices = []
    seen = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            sibling = _bucket_sibling(source_bucket, dx, dy)
            if sibling is None:
                continue
            sibling_index = _bucket_index(sibling)
            if sibling_index in seen:
                continue
            seen.add(sibling_index)
            neighbor_indices.append(sibling_index)
    return neighbor_indices


def _infer_bucket_root(source_path, tile_index):
    source_dir = os.path.dirname(os.path.abspath(source_path))
    expected_tail = os.path.normpath(_bucket_base_path(_bucket_from_index(tile_index)))
    if os.path.normpath(source_dir).endswith(expected_tail):
        return os.path.dirname(os.path.dirname(source_dir))
    return None


def _existing_btg_path(candidates):
    seen = set()
    for candidate in candidates:
        normalized = os.path.abspath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            return normalized
    return None


def _adjacent_btg_paths(source_path):
    tile_index = _tile_index_from_path(source_path)
    if tile_index is None:
        return [], []

    source_dir = os.path.dirname(os.path.abspath(source_path))
    bucket_root = _infer_bucket_root(source_path, tile_index)
    preferred_exts = (".btg.gz", ".btg")
    if source_path.lower().endswith(".btg") and not source_path.lower().endswith(".btg.gz"):
        preferred_exts = (".btg", ".btg.gz")

    resolved_paths = []
    missing_entries = []
    for neighbor_index in _adjacent_bucket_indices(tile_index):
        basename = str(neighbor_index)
        neighbor_bucket = _bucket_from_index(neighbor_index)
        candidates = []
        if bucket_root:
            bucket_dir = os.path.join(bucket_root, _bucket_base_path(neighbor_bucket))
            for ext in preferred_exts:
                candidates.append(os.path.join(bucket_dir, basename + ext))
        for ext in preferred_exts:
            candidates.append(os.path.join(source_dir, basename + ext))

        existing = _existing_btg_path(candidates)
        if existing is None:
            missing_entries.append(
                {
                    "index": neighbor_index,
                    "bucket": neighbor_bucket,
                    "preferred_path": os.path.abspath(candidates[0]) if candidates else "",
                }
            )
            continue
        resolved_paths.append(existing)

    return resolved_paths, missing_entries


def _geodetic_to_ecef(lon_deg, lat_deg, altitude_m=0.0):
    lon = math.radians(float(lon_deg))
    lat = math.radians(float(lat_deg))
    alt = float(altitude_m)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)
    n_val = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n_val + alt) * cos_lat * cos_lon
    y = (n_val + alt) * cos_lat * sin_lon
    z = (n_val * (1.0 - WGS84_E2) + alt) * sin_lat
    return (x, y, z)


def _scene_vertices_from_btg(
    btg_data,
    reference_center=None,
    reference_enu_rot=None,
    reference_z_offset=None,
):
    cx, cy, cz = btg_data.center
    if reference_center is None:
        enu_rot = _ecef_to_enu_matrix(cx, cy, cz)
        scaled_vertices_all = [
            _rotate3((vx * IMPORT_SCALE, vy * IMPORT_SCALE, vz * IMPORT_SCALE), enu_rot)
            for vx, vy, vz in btg_data.vertices
        ]
    else:
        anchor_cx, anchor_cy, anchor_cz = reference_center
        enu_rot = reference_enu_rot or _ecef_to_enu_matrix(anchor_cx, anchor_cy, anchor_cz)
        scaled_vertices_all = [
            _rotate3(
                (
                    ((cx + vx) - anchor_cx) * IMPORT_SCALE,
                    ((cy + vy) - anchor_cy) * IMPORT_SCALE,
                    ((cz + vz) - anchor_cz) * IMPORT_SCALE,
                ),
                enu_rot,
            )
            for vx, vy, vz in btg_data.vertices
        ]

    if scaled_vertices_all:
        mean_z = (
            float(reference_z_offset)
            if reference_z_offset is not None
            else sum(v[2] for v in scaled_vertices_all) / len(scaled_vertices_all)
        )
        scaled_vertices_all = [(x, y, z - mean_z) for x, y, z in scaled_vertices_all]
    else:
        mean_z = float(reference_z_offset) if reference_z_offset is not None else 0.0

    return scaled_vertices_all, mean_z


def _ecef_to_enu_matrix(cx, cy, cz):
    lon = math.atan2(cy, cx)
    lat = math.atan2(cz, math.sqrt(cx * cx + cy * cy))
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    return (
        (-sin_lon, cos_lon, 0.0),
        (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat),
        (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat),
    )


def _rotate3(v, r_mat):
    x, y, z = v
    return (
        r_mat[0][0] * x + r_mat[0][1] * y + r_mat[0][2] * z,
        r_mat[1][0] * x + r_mat[1][1] * y + r_mat[1][2] * z,
        r_mat[2][0] * x + r_mat[2][1] * y + r_mat[2][2] * z,
    )


def _rotate3_inv(v, r_mat):
    x, y, z = v
    return (
        r_mat[0][0] * x + r_mat[1][0] * y + r_mat[2][0] * z,
        r_mat[0][1] * x + r_mat[1][1] * y + r_mat[2][1] * z,
        r_mat[0][2] * x + r_mat[1][2] * y + r_mat[2][2] * z,
    )


def _normalize3(v):
    x, y, z = v
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    inv_length = 1.0 / length
    return (x * inv_length, y * inv_length, z * inv_length)


def _encode_normal_component(value):
    clamped = max(-1.0, min(1.0, float(value)))
    encoded = int(round((clamped + 1.0) * 127.5))
    return max(0, min(255, encoded))
