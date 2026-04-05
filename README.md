# FlightGear BTG Blender Add-on by Federico Contreras

0.0.4 Broke up addon into different files, the single file script it was becoming way too huge.
0.0.3 Added workflow to reliably match vertices from an inner tile (like an airport) and the outer tile. 
0.0.2 Fixed crash FlightGear diaplying b0rked testires due to large positive UV issue on non-repeating textures
0.0.1 Initial release

Blender 4.x add-on for importing, editing, and exporting FlightGear TerraGear `.btg` and `.btg.gz` terrain tiles.

## Installation

Build an installable Blender add-on ZIP from the repository root:

```bash
make package
```
or:

```bash
python3 build_blender_addon_zip.py
```

The command writes a versioned ZIP file into `releases/`.

1. In Blender, open `Edit > Preferences > Add-ons`.
2. Choose `Install from Disk...`.
3. Select the generated `blender-btg-import-export-<version>.zip` file.
4. Enable the `FlightGear BTG Import/Export` add-on.

## Current Feature Set

- Import `.btg` and `.btg.gz` tiles directly from Blender.
- Import at 1% scale so large terrain tiles remain workable in Blender.
- Rebuild textured Blender materials from FlightGear terrain textures.
- Optionally flip DDS V coordinates on import and reverse that flip on export.
- Load the 8 adjacent FlightGear buckets around the active tile for seam alignment.
- Generate exportable ocean placeholder neighbors when adjacent ocean BTGs are missing.
- Manage adjacent reference tile display from the 3D View sidebar:
  - textured or wire display
  - in-front drawing
  - selection lock/unlock
  - one-click seam editing preset
- Cache the FlightGear material library from `materials.xml`.
- Add one FlightGear material at a time through a search popup.
- Clear or unpin cached library materials.
- Export BTG tiles back to `.btg` or `.btg.gz`.
- Write or update a sibling `.stg` with `OBJECT_BASE` automatically.
- Optionally copy exported BTG and STG files into a valid FlightGear scenery package layout.
- Sync user-authored materials into `materials.xml` and copy their referenced textures into `FG_ROOT/Textures/<subfolder>`.
- Preserve imported native FlightGear materials while skipping unnecessary managed `materials.xml` rewrites.
- Detect custom texture overrides on imported FlightGear materials and export them as user-managed materials.
- Export BTG point-light groups using the expected FlightGear naming convention.
- Author explicit FlightGear material properties from Blender's Material tab.

## Blender UI Overview

### Import

Available from `File > Import > FlightGear Terrain (.btg/.btg.gz)`.

Key options:

- `Create Textured Materials`: build Blender materials from the configured FlightGear texture root.
- `Texture Root Override`: temporary override for the terrain texture directory.
- `Flip DDS V For Blender View`: keeps DDS-backed surfaces visually aligned with PNG-backed ones inside Blender.
- `Load 8 Adjacent Tiles`: loads neighboring buckets immediately after importing the main tile.
- `Create Ocean Placeholders For Missing Adjacent Tiles`: generates placeholder ocean tiles for missing neighbors.

### Export

Available from `File > Export > FlightGear Terrain (.btg/.btg.gz)`.

Key options:

- `Selected Objects Only`: exports only the current mesh selection.
- `Flip DDS V For Blender View`: reverses the Blender viewport DDS flip so FlightGear UVs remain correct.
- `Write Associated .stg`: creates or updates the sibling `.stg` with `OBJECT_BASE`.
- `Export Scenery Package Layout`: copies the exported tile into `Terrain/<10deg>/<1deg>/` under a chosen scenery package root.
- `Sync User Materials To materials.xml`: writes exporter-managed material definitions and copies textures.
- `Overwrite Existing Materials`: replaces existing `materials.xml` entries with the same names.
- `Overwrite Existing Texture Files`: replaces copied textures in the destination texture subfolder.

### 3D View Sidebar

Available in `View3D > Sidebar > FlightGear > FlightGear BTG`.

Sections:

- `Material Library`: cache all FlightGear materials, add one by search, refresh, or clear cached materials.
- `Active Tile`: shows the selected imported BTG tile and adjacent-tile state.
- `Display Helpers`: toggle adjacent tiles between wire and textured display, enable in-front drawing, lock selection, or apply the seam-edit preset.

### Material Properties

Available in `Material Properties > FlightGear` for the active Blender material.

The panel provides:

- Preview of export name, bound texture, and material-sync status.
- Presets for:
  - `Generic Terrain`
  - `Runway / Taxiway`
  - `Overlay / Decal`
  - `Custom Advanced`
- Export override controls for:
  - `Effect`
  - physical texture size (`xsize`, `ysize`)
  - wrap flags (`wrapu`, `wrapv`)
  - optional solid override
  - optional friction, rolling friction, bumpiness, and load resistance overrides

This is the main workflow for brand-new Blender materials that need explicit FlightGear material semantics on export.

## Typical Workflow

1. Set `Terrain Texture Root` in the add-on preferences to a path under your FlightGear `FG_ROOT/Textures` tree.
2. Import a `.btg` or `.btg.gz` tile.
3. Optionally load adjacent reference tiles for seam work.
4. Edit terrain meshes and materials in Blender.
5. For new materials, open `Material Properties > FlightGear` and enable material overrides or apply a preset.
6. Export the tile.
7. If needed, enable `Sync User Materials To materials.xml` and `Export Scenery Package Layout` so the tile, STG, material entries, and textures land in a usable FlightGear scenery package.

## Preferences

The add-on preferences expose two important paths:

- `Terrain Texture Root`: used to resolve terrain textures and infer `FG_ROOT` during export.
- `Material Map JSON`: optional manual mapping file for resolving BTG material names to exact texture files.

Default texture root in the add-on source is `/games/flightgear-2024/Textures/Terrain`.