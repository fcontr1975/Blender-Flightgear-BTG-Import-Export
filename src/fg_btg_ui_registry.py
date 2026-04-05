def apply_class_properties(ns):
    string_property = ns["StringProperty"]
    bool_property = ns["BoolProperty"]
    enum_property = ns["EnumProperty"]
    float_property = ns["FloatProperty"]
    int_property = ns["IntProperty"]

    ns["FlightGearBTGPreferences"].__annotations__["texture_root"] = string_property(
        name="Terrain Texture Root",
        description="Path to FlightGear Terrain textures used for imported Blender materials",
        subtype="DIR_PATH",
        default=ns["DEFAULT_TEXTURE_ROOT"],
    )
    ns["FlightGearBTGPreferences"].__annotations__["material_map_path"] = string_property(
        name="Material Map JSON",
        description="Optional JSON file mapping BTG material names to exact texture files",
        subtype="FILE_PATH",
        default="",
    )

    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["filter_glob"] = string_property(
        default="*.btg;*.btg.gz",
        options={"HIDDEN"},
    )
    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["create_materials"] = bool_property(
        name="Create Textured Materials",
        description="Create Blender materials using the configured FlightGear terrain texture root",
        default=True,
    )
    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["texture_root"] = string_property(
        name="Texture Root Override",
        description="Optional override for the FlightGear Terrain texture directory",
        subtype="DIR_PATH",
        default="",
    )
    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["flip_dds_v_for_view"] = bool_property(
        name="Flip DDS V For Blender View",
        description="Flip V coordinates for DDS-backed materials on import so DDS and PNG runway markings look consistent in Blender",
        default=True,
    )
    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["load_adjacent_tiles"] = bool_property(
        name="Load 8 Adjacent Tiles",
        description="Compute the 8 neighboring FlightGear buckets from the selected tile name and import them around the main tile for reference and vertex snapping",
        default=False,
    )
    ns["IMPORT_SCENE_OT_flightgear_btg"].__annotations__["create_ocean_placeholders_for_missing_adjacent"] = bool_property(
        name="Create Ocean Placeholders For Missing Adjacent Tiles",
        description="When neighboring bucket BTG files are missing (commonly pure ocean), generate exportable placeholder ocean tiles with correct bucket metadata",
        default=False,
    )
    ns["OBJECT_OT_flightgear_load_adjacent_tiles"].__annotations__["flip_dds_v_for_view"] = bool_property(
        name="Flip DDS V For Blender View",
        description="Flip V coordinates for DDS-backed materials on adjacent reference imports so DDS and PNG runway markings look consistent in Blender",
        default=True,
    )
    ns["OBJECT_OT_flightgear_load_adjacent_tiles"].__annotations__["create_ocean_placeholders_for_missing_adjacent"] = bool_property(
        name="Create Ocean Placeholders For Missing Adjacent Tiles",
        description="When neighboring bucket BTG files are missing (commonly pure ocean), generate exportable placeholder ocean tiles with correct bucket metadata",
        default=False,
    )
    ns["OBJECT_OT_flightgear_adjacent_display_mode"].__annotations__["display_mode"] = string_property(
        name="Display Mode",
        description="Viewport display mode to apply to adjacent reference tiles",
        default="TEXTURED",
    )
    ns["OBJECT_OT_flightgear_adjacent_show_in_front"].__annotations__["show_in_front"] = bool_property(
        name="Show In Front",
        description="Whether adjacent reference tiles should draw in front of the main tile in the viewport",
        default=False,
    )
    ns["OBJECT_OT_flightgear_adjacent_selectable"].__annotations__["selectable"] = bool_property(
        name="Selectable",
        description="Whether adjacent reference tiles can be selected in the viewport",
        default=True,
    )
    ns["OBJECT_OT_flightgear_retarget_tile"].__annotations__["target_tile_index"] = int_property(
        name="Target Tile Index",
        description="FlightGear tile index used to recalculate BTG center and source metadata",
        default=0,
        min=0,
    )
    ns["OBJECT_OT_flightgear_retarget_tile"].__annotations__["rename_objects"] = bool_property(
        name="Rename Tile Objects",
        description="Rename the active tile object and point-light children when their names start with the old tile index",
        default=True,
    )
    ns["OBJECT_OT_flightgear_conform_seam_vertices"].__annotations__["working_tile_name"] = string_property(
        name="Working Mesh",
        description="Mesh whose seam vertices will be moved. Defaults to the active object",
        default="",
    )
    ns["OBJECT_OT_flightgear_conform_seam_vertices"].__annotations__["reference_tile_name"] = string_property(
        name="Reference Mesh",
        description="Mesh used as the target seam surface. Leave empty to use loaded adjacent references",
        default="",
    )
    ns["OBJECT_OT_flightgear_conform_seam_vertices"].__annotations__["target_vertices"] = enum_property(
        name="Target Vertices",
        description="Which working-mesh vertices should be conformed",
        items=(
            ("SELECTED", "Selected Vertices", "Conform only selected vertices (Edit Mode)"),
            ("BOUNDARY", "Boundary Vertices", "Conform all boundary vertices on the working mesh"),
        ),
        default="SELECTED",
    )
    ns["OBJECT_OT_flightgear_conform_seam_vertices"].__annotations__["snap_mode"] = enum_property(
        name="Snap Mode",
        description="Choose whether to copy only altitude or full coordinates from the nearest reference seam vertex",
        items=(
            ("Z_ONLY", "Z Only", "Keep X/Y and copy only Z from nearest reference seam vertex"),
            ("XYZ", "XYZ", "Copy full XYZ from nearest reference seam vertex"),
        ),
        default="Z_ONLY",
    )
    ns["OBJECT_OT_flightgear_conform_seam_vertices"].__annotations__["horizontal_tolerance_m"] = float_property(
        name="Horizontal Tolerance (m)",
        description="Maximum horizontal seam distance used when pairing working vertices to reference vertices",
        default=0.20,
        min=0.001,
        soft_max=5.0,
    )
    ns["OBJECT_OT_flightgear_set_vertices_in_game_altitude"].__annotations__["working_tile_name"] = string_property(
        name="Working Mesh",
        description="Mesh whose vertices will be set to the chosen in-game altitude. Defaults to the active object",
        default="",
    )
    ns["OBJECT_OT_flightgear_set_vertices_in_game_altitude"].__annotations__["target_vertices"] = enum_property(
        name="Target Vertices",
        description="Which working-mesh vertices should be set to the chosen in-game altitude",
        items=(
            ("SELECTED", "Selected Vertices", "Set only selected vertices (Edit Mode)"),
            ("BOUNDARY", "Boundary Vertices", "Set all boundary vertices on the working mesh"),
        ),
        default="SELECTED",
    )
    ns["OBJECT_OT_flightgear_set_vertices_in_game_altitude"].__annotations__["altitude_m"] = float_property(
        name="In-Game Altitude (m)",
        description="Target altitude in FlightGear meters; 0.0 corresponds to sea level",
        default=0.0,
    )
    ns["OBJECT_OT_flightgear_cache_fg_material_library"].__annotations__["materials_xml_path"] = string_property(
        name="materials.xml Path Override",
        description="Optional full path to FlightGear materials.xml. Leave empty to auto-use FG_ROOT/Materials/regions/materials.xml",
        subtype="FILE_PATH",
        default="",
    )
    ns["OBJECT_OT_flightgear_cache_fg_material_library"].__annotations__["force_refresh_cache"] = bool_property(
        name="Force Refresh materials.xml Cache",
        description="Re-read materials.xml from disk even if the parser cache is populated",
        default=False,
    )
    ns["OBJECT_OT_flightgear_cache_fg_material_library"].__annotations__["refresh_existing_materials"] = bool_property(
        name="Refresh Existing Blender Materials",
        description="Rebuild already existing materials from FlightGear definitions instead of leaving them untouched",
        default=False,
    )
    ns["OBJECT_OT_flightgear_cache_fg_material_library"].__annotations__["keep_materials_persistent"] = bool_property(
        name="Keep Materials Persistent",
        description="Enable fake users so cached FlightGear materials survive save/reload even when not assigned",
        default=True,
    )
    ns["OBJECT_OT_flightgear_add_fg_material_from_library"].__annotations__["material_name"] = enum_property(
        name="FlightGear Material",
        description="Search and select a FlightGear material from materials.xml",
        items=ns["_fg_material_library_enum_items"],
    )
    ns["OBJECT_OT_flightgear_add_fg_material_from_library"].__annotations__["keep_material_persistent"] = bool_property(
        name="Keep Material Persistent",
        description="Enable fake user so this material survives save/reload even when not assigned",
        default=True,
    )
    ns["OBJECT_OT_flightgear_clear_cached_material_library"].__annotations__["remove_used_materials"] = bool_property(
        name="Remove Materials In Use",
        description="Also remove cached materials currently assigned to objects (use with caution)",
        default=False,
    )
    ns["OBJECT_OT_flightgear_clear_cached_material_library"].__annotations__["clear_fake_user_only"] = bool_property(
        name="Only Clear Fake Users",
        description="Keep materials but disable fake users so unused ones can be purged naturally",
        default=False,
    )

    ns["FlightGearMaterialSettings"].__annotations__["enabled"] = bool_property(
        name="Enable FlightGear Overrides",
        description="Export this Blender material with explicit FlightGear material settings",
        default=False,
    )
    ns["FlightGearMaterialSettings"].__annotations__["preset"] = enum_property(
        name="FlightGear Preset",
        description="Starter preset for common FlightGear terrain material types",
        items=(
            ("GENERIC_TERRAIN", "Generic Terrain", "Use Effects/terrain-default with repeating terrain settings"),
            ("RUNWAY_TAXIWAY", "Runway / Taxiway", "Use Effects/runway with pavement-like defaults"),
            ("OVERLAY_DECAL", "Overlay / Decal", "Use Effects/terrain-overlay for alpha-driven overlays"),
            ("CUSTOM", "Custom Advanced", "Edit all FlightGear material fields manually"),
        ),
        default="GENERIC_TERRAIN",
    )
    ns["FlightGearMaterialSettings"].__annotations__["effect"] = string_property(
        name="Effect",
        description="FlightGear effect path written to materials.xml",
        default="Effects/terrain-default",
    )
    ns["FlightGearMaterialSettings"].__annotations__["xsize"] = float_property(
        name="Texture Size X",
        description="Physical repetition size of the material in meters along the X axis",
        default=1000.0,
        min=0.0,
    )
    ns["FlightGearMaterialSettings"].__annotations__["ysize"] = float_property(
        name="Texture Size Y",
        description="Physical repetition size of the material in meters along the Y axis",
        default=1000.0,
        min=0.0,
    )
    ns["FlightGearMaterialSettings"].__annotations__["wrapu"] = bool_property(
        name="Wrap U",
        description="Repeat the texture horizontally in FlightGear",
        default=True,
    )
    ns["FlightGearMaterialSettings"].__annotations__["wrapv"] = bool_property(
        name="Wrap V",
        description="Repeat the texture vertically in FlightGear",
        default=True,
    )
    ns["FlightGearMaterialSettings"].__annotations__["override_solid"] = bool_property(
        name="Override Solid",
        description="Write an explicit <solid> property into materials.xml",
        default=False,
    )
    ns["FlightGearMaterialSettings"].__annotations__["solid"] = bool_property(
        name="Solid",
        description="Whether the surface should be treated as solid in FlightGear",
        default=True,
    )
    ns["FlightGearMaterialSettings"].__annotations__["override_physics"] = bool_property(
        name="Override Physics",
        description="Write explicit friction, bumpiness, and load values into materials.xml",
        default=False,
    )
    ns["FlightGearMaterialSettings"].__annotations__["friction_factor"] = float_property(
        name="Friction Factor",
        description="FlightGear friction-factor value for this surface",
        default=0.8,
    )
    ns["FlightGearMaterialSettings"].__annotations__["rolling_friction"] = float_property(
        name="Rolling Friction",
        description="FlightGear rolling-friction value for this surface",
        default=0.05,
    )
    ns["FlightGearMaterialSettings"].__annotations__["bumpiness"] = float_property(
        name="Bumpiness",
        description="FlightGear bumpiness value for this surface",
        default=0.05,
    )
    ns["FlightGearMaterialSettings"].__annotations__["load_resistance"] = float_property(
        name="Load Resistance",
        description="FlightGear load-resistance value for this surface",
        default=100000.0,
        min=0.0,
    )

    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["filter_glob"] = string_property(
        default="*.btg;*.btg.gz",
        options={"HIDDEN"},
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["export_selected"] = bool_property(
        name="Selected Objects Only",
        description="Only export selected mesh objects",
        default=True,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["sync_materials_xml"] = bool_property(
        name="Sync User Materials To materials.xml",
        description="Write exported BTG material names into FlightGear materials.xml and copy referenced texture images",
        default=True,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["write_associated_stg"] = bool_property(
        name="Write Associated .stg",
        description="Create or update the sibling .stg file with an OBJECT_BASE entry that points at the exported BTG",
        default=True,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["export_scenery_package_layout"] = bool_property(
        name="Export Scenery Package Layout",
        description="Also copy the exported BTG/STG into a FlightGear scenery tree at Terrain/<10deg>/<1deg>/ using the tile index filename",
        default=False,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["scenery_package_root"] = string_property(
        name="Scenery Package Root",
        description="Root folder to receive FlightGear scenery layout (for example .../CustomAddons/Scenery)",
        subtype="DIR_PATH",
        default="",
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["materials_xml_path"] = string_property(
        name="materials.xml Path Override",
        description="Optional full path to materials.xml. Leave empty to auto-use FG_ROOT/Materials/regions/materials.xml",
        subtype="FILE_PATH",
        default="",
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["texture_subfolder"] = string_property(
        name="Texture Subfolder Under FG_ROOT/Textures",
        description="Destination folder for copied material textures",
        default="bfg-exporter",
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["overwrite_existing_materials"] = bool_property(
        name="Overwrite Existing Materials",
        description="If enabled, replace existing material definitions with the same name when syncing",
        default=False,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["overwrite_texture_files"] = bool_property(
        name="Overwrite Existing Texture Files",
        description="If enabled, copied textures can replace existing files in the destination folder",
        default=False,
    )
    ns["EXPORT_SCENE_OT_flightgear_btg"].__annotations__["flip_dds_v_for_view"] = bool_property(
        name="Flip DDS V For Blender View",
        description="Reverse the Blender DDS view flip on export so BTG UVs remain FlightGear-correct",
        default=True,
    )

    ns["EXPORT_SCENE_OT_wavefront_obj"].__annotations__["filter_glob"] = string_property(
        default="*.obj",
        options={"HIDDEN"},
    )
    ns["EXPORT_SCENE_OT_wavefront_obj"].__annotations__["export_selected"] = bool_property(
        name="Selected Objects Only",
        description="Only export selected mesh objects",
        default=True,
    )
    ns["EXPORT_SCENE_OT_wavefront_obj"].__annotations__["apply_btg_scale"] = bool_property(
        name="Apply BTG Scale Compensation",
        description="Export with x100 scale so imported BTG scenery returns to its original size in external 3D tools",
        default=False,
    )
    ns["EXPORT_SCENE_OT_wavefront_obj"].__annotations__["include_textures"] = bool_property(
        name="Write MTL And Textures",
        description="Write an MTL file and resolve texture paths using the configured FlightGear texture roots",
        default=True,
    )


def make_menu_functions(ns):
    def menu_func_import(self, _context):
        self.layout.operator(
            ns["IMPORT_SCENE_OT_flightgear_btg"].bl_idname,
            text="FlightGear Terrain (.btg/.btg.gz)",
        )

    def menu_func_export(self, _context):
        self.layout.operator(
            ns["EXPORT_SCENE_OT_flightgear_btg"].bl_idname,
            text="FlightGear Terrain (.btg/.btg.gz)",
        )
        self.layout.operator(
            ns["EXPORT_SCENE_OT_wavefront_obj"].bl_idname,
            text="Wavefront OBJ (.obj)",
        )

    def menu_func_object(self, _context):
        self.layout.separator()
        self.layout.operator(
            ns["OBJECT_OT_flightgear_load_adjacent_tiles"].bl_idname,
            text="Load Adjacent FlightGear Tiles",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_clear_adjacent_tiles"].bl_idname,
            text="Remove Adjacent FlightGear Tiles",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_retarget_tile"].bl_idname,
            text="Retarget Tile",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_conform_seam_vertices"].bl_idname,
            text="Conform Selected Seam Vertices",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_set_vertices_in_game_altitude"].bl_idname,
            text="Set Vertices at a Specific In-Game Altitude",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_cache_fg_material_library"].bl_idname,
            text="Cache FlightGear Material Library",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_add_fg_material_from_library"].bl_idname,
            text="Add FlightGear Material (Search)",
        )
        self.layout.operator(
            ns["OBJECT_OT_flightgear_clear_cached_material_library"].bl_idname,
            text="Clear Cached FlightGear Materials",
        )

    return menu_func_import, menu_func_export, menu_func_object


def build_classes(ns):
    return (
        ns["FlightGearBTGPreferences"],
        ns["FlightGearMaterialSettings"],
        ns["IMPORT_SCENE_OT_flightgear_btg"],
        ns["EXPORT_SCENE_OT_flightgear_btg"],
        ns["EXPORT_SCENE_OT_wavefront_obj"],
        ns["OBJECT_OT_flightgear_load_adjacent_tiles"],
        ns["OBJECT_OT_flightgear_clear_adjacent_tiles"],
        ns["OBJECT_OT_flightgear_adjacent_display_mode"],
        ns["OBJECT_OT_flightgear_adjacent_show_in_front"],
        ns["OBJECT_OT_flightgear_adjacent_selectable"],
        ns["OBJECT_OT_flightgear_adjacent_edit_preset"],
        ns["OBJECT_OT_flightgear_retarget_tile"],
        ns["OBJECT_OT_flightgear_set_working_mesh_from_active"],
        ns["OBJECT_OT_flightgear_set_reference_mesh_from_selection"],
        ns["OBJECT_OT_flightgear_conform_seam_vertices"],
        ns["OBJECT_OT_flightgear_set_vertices_in_game_altitude"],
        ns["OBJECT_OT_flightgear_cache_fg_material_library"],
        ns["OBJECT_OT_flightgear_add_fg_material_from_library"],
        ns["OBJECT_OT_flightgear_clear_cached_material_library"],
        ns["MATERIAL_OT_flightgear_apply_preset"],
        ns["MATERIAL_PT_flightgear_material"],
        ns["VIEW3D_PT_flightgear_btg_tools"],
    )


def register_addon(
    bpy_module,
    classes,
    material_settings_class,
    menu_func_import,
    menu_func_export,
    menu_func_object,
    pointer_property,
    string_property,
    bool_property=None,
):
    if bool_property is None:
        bool_property = bpy_module.props.BoolProperty

    for cls in classes:
        bpy_module.utils.register_class(cls)

    bpy_module.types.Material.fg_btg = pointer_property(type=material_settings_class)
    bpy_module.types.Scene.fg_btg_working_mesh_name = string_property(
        name="Working Mesh",
        description="Mesh whose seam vertices will be conformed",
        default="",
    )
    bpy_module.types.Scene.fg_btg_reference_mesh_name = string_property(
        name="Reference Mesh",
        description="Mesh used as seam conformity reference",
        default="",
    )
    bpy_module.types.Scene.fg_btg_ui_material_library_expanded = bool_property(
        name="Material Library Expanded",
        default=True,
    )
    bpy_module.types.Scene.fg_btg_ui_adjacent_tiles_expanded = bool_property(
        name="Adjacent Tiles Expanded",
        default=True,
    )
    bpy_module.types.Scene.fg_btg_ui_tile_metadata_expanded = bool_property(
        name="Tile Metadata Expanded",
        default=True,
    )
    bpy_module.types.Scene.fg_btg_ui_display_helpers_expanded = bool_property(
        name="Display Helpers Expanded",
        default=True,
    )
    bpy_module.types.Scene.fg_btg_ui_tile_pair_conform_expanded = bool_property(
        name="Tile Pair Conform Expanded",
        default=True,
    )

    bpy_module.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy_module.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy_module.types.VIEW3D_MT_object.append(menu_func_object)


def unregister_addon(
    bpy_module,
    classes,
    menu_func_import,
    menu_func_export,
    menu_func_object,
):
    bpy_module.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy_module.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy_module.types.VIEW3D_MT_object.remove(menu_func_object)

    if hasattr(bpy_module.types.Material, "fg_btg"):
        del bpy_module.types.Material.fg_btg
    if hasattr(bpy_module.types.Scene, "fg_btg_working_mesh_name"):
        del bpy_module.types.Scene.fg_btg_working_mesh_name
    if hasattr(bpy_module.types.Scene, "fg_btg_reference_mesh_name"):
        del bpy_module.types.Scene.fg_btg_reference_mesh_name
    if hasattr(bpy_module.types.Scene, "fg_btg_ui_material_library_expanded"):
        del bpy_module.types.Scene.fg_btg_ui_material_library_expanded
    if hasattr(bpy_module.types.Scene, "fg_btg_ui_adjacent_tiles_expanded"):
        del bpy_module.types.Scene.fg_btg_ui_adjacent_tiles_expanded
    if hasattr(bpy_module.types.Scene, "fg_btg_ui_tile_metadata_expanded"):
        del bpy_module.types.Scene.fg_btg_ui_tile_metadata_expanded
    if hasattr(bpy_module.types.Scene, "fg_btg_ui_display_helpers_expanded"):
        del bpy_module.types.Scene.fg_btg_ui_display_helpers_expanded
    if hasattr(bpy_module.types.Scene, "fg_btg_ui_tile_pair_conform_expanded"):
        del bpy_module.types.Scene.fg_btg_ui_tile_pair_conform_expanded

    for cls in reversed(classes):
        bpy_module.utils.unregister_class(cls)
