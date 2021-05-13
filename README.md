## TS2 GMDC Importer/Exporter for Blender 2.80+

This add-on supports rigging data, two UV layers, morphs, and bounding geometry.

#### Installation
1. Run Blender and change area to Preferences;
2. Choose "Add-ons" and press "Install...";
3. Install by selecting the io\_ts2\_gmdc.zip file;
4. Finally, enable "Import-Export: TS2 GMDC Importer/Exporter". (For easier navigation you may filter the list of add-ons by selecting "Import-Export" from the drop down list.

#### Importing
The importer works in two modes, Geometry and Skeleton.
To view the options, press the top right toggle button in the file selection window (if not already shown).
Geometry mode is used to import meshes from GMDC files, i.e., new mesh objects are added to the scene.
In Skeleton mode the importer loads data from CRES file, creates an armature object, and assigns armature modifiers to mesh objects.
In general, armature is not necessary for mesh editing, but may be helpful.

Key features:
* Bones are imported as vertex groups and initially named as "bone#{bone\_idx}", that is, bone index is written after the number sign. Although bone names can be changed, **do not delete or modify bone indices!** Otherwise, the exporter will most likely throw errors, since bone indices are extracted from vertex group names.
* Morphs are imported as shape keys.
* Inverse transforms from GMDC files are saved in scene properties. This data is used by the exporter and included into generated GMDC file.
* Seams can be removed by geometry reindexing (the "Remove doubles" option).

#### Links:
* [Official Blender Website](https://www.blender.org/)
