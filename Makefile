.PHONY: package package-clean

# Build a Blender-installable addon zip into archive-releases/.
package:
	python3 build_blender_addon_zip.py


# we want to generally keep old versions, If necessary we can do this manually.
# Remove generated addon zip artifacts.
# package-clean:
#	rm -f releases/blender-btg-import-export-*.zip
