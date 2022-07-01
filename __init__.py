#-------------------------------------------------------------------------------
# Copyright (C) 2021  DjAlex88 (https://github.com/djalex88/)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#-------------------------------------------------------------------------------

bl_info = {
	"name": "TS2 GMDC Importer/Exporter",
	"description": "Import-Export TS2 GMDC, Import skeleton from CRES.",
	"author": "DjAlex88 (https://github.com/djalex88/)",
	"version": (0, 91, 2),
	"blender": (2, 80, 0),
	"location": "File > Import > Import TS2 GMDC (.5gd, .gmdc)",
	"category": "Import-Export",
}

import bpy
from bpy.props import BoolProperty, StringProperty, FloatProperty, EnumProperty, PointerProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

class Import_GMDC(bpy.types.Operator, ImportHelper):
	"""Import TS2 GMDC"""

	bl_idname = "import_scene.ts2_gmdc"
	bl_label = "Import TS2 GMDC"
	bl_options = {'REGISTER', 'UNDO'}

	filename_ext = ".gmdc"

	filepath : StringProperty(subtype='FILE_PATH')

	import_mode : EnumProperty(
			items = [
				('GEOMETRY', "Geometry", "Import data from GMDC file", 'MESH_DATA', 0),
				('SKELETON', "Skeleton", "Import data from CRES file", 'ARMATURE_DATA', 1),
				],
			default     = 'GEOMETRY',
			name        = "Mode",
			description = "Import mode" )

	# geometry (GMDC file)
	#
	remove_doubles : BoolProperty(
			name        = "Remove doubles",
			description = "If some vertices differ only in texture coordinates, then they are fused together (removes seams)",
			default     = True )

	import_bmesh : BoolProperty(
			name        = "Bounding geometry",
			description = "Import bounding geometry",
			default     = False )

	replace_inv_t : BoolProperty(
			name        = "Replace inverse transforms",
			description = "If the scene already has inverse transforms set, they will be replaced",
			default     = False )

	# skeleton (CRES file)
	#
	selected_only : BoolProperty(
			name        = "Only for selected objects",
			description = "Import skeleton and create armature modifier only for selected objects",
			default     = True )

	all_bones : BoolProperty(
			name        = "All bones / transforms",
			description = "Import all bones/transforms; otherwise, used bones only",
			default     = False )

	# other
	#
	save_log : BoolProperty(
			name        = "Save log",
			description = "Save log info into file *.import_log.txt",
			default     = False )


	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

	def execute(self, context):
		from .gmdc_import import begin_import
		begin_import(
			self.filepath,
			context.scene,
			settings={
			    'import_mode' : self.import_mode,
			 'remove_doubles' : self.remove_doubles,
			   'import_bmesh' : self.import_bmesh,
			  'replace_inv_t' : self.replace_inv_t,
			  'selected_only' : self.selected_only,
			      'all_bones' : self.all_bones,
			       'save_log' : self.save_log,
			})
		return {'FINISHED'}

	def draw(self, context):
		box = self.layout.box()
		box.prop(self, 'import_mode')
		if self.import_mode == 'GEOMETRY':
			box.prop(self, 'remove_doubles')
			box.prop(self, 'import_bmesh')
			box.prop(self, 'replace_inv_t')
		if self.import_mode == 'SKELETON':
			box.prop(self, 'selected_only')
			box.prop(self, 'all_bones')
		box = self.layout.box()
		box.label(text="Other", icon='MODIFIER')
		box.prop(self, 'save_log')


#---------------------------------------

# scans ./target dir and returns list of items
def load_target_file_items():
	import os
	target_dir = os.path.join(os.path.dirname(__file__), 'target')
	items = []
	try:
		file_names = os.listdir(target_dir)
	except:
		pass
	else:
		for name in file_names:
			path = os.path.join(target_dir, name)
			if os.path.isfile(path):
				items.append((path, name, ""))
	return items

class Export_GMDC(bpy.types.Operator, ExportHelper):
	"""Export TS2 GMDC"""

	bl_idname = "export_scene.ts2_gmdc"
	bl_label = "Export TS2 GMDC"
	bl_options = {'REGISTER'}

	filename_ext = ".gmdc"

	filepath : StringProperty(subtype='FILE_PATH')

	# main properties
	#
	selected_only : BoolProperty(
			name        = "Only selected objects",
			description = "Export only selected objects",
			default     = False )

	apply_transforms : BoolProperty(
			name        = "Apply rotation & scale",
			description = "Apply rotation and scaling to mesh objects",
			default     = True )

	export_rigging : BoolProperty(
			name        = "Rigging data",
			description = "Export rigging data (bone indices, weights)",
			default     = False )

	export_tangents : BoolProperty(
			name        = "Tangents",
			description = "Calculate and export tangent vectors (required for bump mapping)",
			default     = False )

	export_bmesh : BoolProperty(
			name        = "Bounding geometry",
			description = "Create mesh object for bounding geometry (if any)",
			default     = False )

	bmesh_name : StringProperty(
			name        = "Obj. name",
			description = "Name of mesh object of bounding geometry",
			default     = "b_mesh" )

	bmesh_threshold : FloatProperty(
			name        = "Bone weight threshold",
			description = "Minimum bone weight required to include a triangle into bounding mesh",
			default     = 0.5,
			min         = 0.05,
			max         = 1,
			step        = 0.05,
			precision   = 2 )

	export_morphs : EnumProperty(
			items = [
				('0', "Do not export morphs", "Ignore shape keys (if exist); no morph data created"),
				('1', "Diff. in v.coords only", "Use only vertex coordinates to calculate morph data"),
				('2', "Diff. in v.coords and normals", "Calculate morph data from vertex coordinates and normals"),
				],
			default     = '0',
			name        = "Morphs",
			description = "Calculate morph data from shape keys" )

	align_normals : BoolProperty(
			name        = "Align normals",
			description = "Align normals of vertices connecting to head mesh",
			default     = False )

	align_target : EnumProperty(
			items = load_target_file_items(),
			default     = None,
			name        = "Target",
			description = "Reference mesh to align normals to" )

	resource_name : StringProperty(
			name        = "SGResource",
			description = "SGResource name of this geometry",
			default     = "" )

	# other
	#
	name_suffix : BoolProperty(
			name        = "_tslocator_gmdc",
			description = "Add default suffix",
			default     = True )

	use_obj_props : BoolProperty(
			name        = "Use object properties",
			description = "Custom properties for objects (e.g. flags, name). See object properties panel",
			default     = False )

	save_log : BoolProperty(
			name        = "Save log",
			description = "Save log info into file *.export_log.txt",
			default     = False )


	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

	def execute(self, context):
		from .gmdc_export import begin_export
		begin_export(
			bpy.path.ensure_ext(self.filepath, self.filename_ext),
			context.scene,
			settings={
			   'selected_only' : self.selected_only,
			'apply_transforms' : self.apply_transforms,
			  'export_rigging' : self.export_rigging,
			 'export_tangents' : self.export_tangents,
			    'export_bmesh' : self.export_bmesh,
			      'bmesh_name' : self.bmesh_name.strip(),
			 'bmesh_threshold' : self.bmesh_threshold,
			   'export_morphs' : int(self.export_morphs),
			   'align_normals' : self.align_normals,
			    'align_target' : self.align_target,
			   'resource_name' : self.resource_name.strip(),
			     'name_suffix' : self.name_suffix,
			   'use_obj_props' : self.use_obj_props,
			        'save_log' : self.save_log,
			})
		return {'FINISHED'}

	def draw(self, context):
		box = self.layout.box()
		box.label(text="Geometry", icon='MESH_DATA')
		box.prop(self, 'selected_only')
		box.prop(self, 'apply_transforms')
		box.prop(self, 'export_rigging')
		box.prop(self, 'export_tangents')
		box.prop(self, 'export_morphs')
		box.prop(self, 'align_normals')
		if self.align_normals:
			box.prop(self, 'align_target')
		box.prop(self, 'export_bmesh')
		if self.export_bmesh:
			box.prop(self, 'bmesh_name')
			box.prop(self, 'bmesh_threshold')
		box = self.layout.box()
		box.label(text="Other", icon='MODIFIER')
		box.label(text="SGResource:")
		row = box.split(factor=0.5, align=True)
		row.prop(self, 'resource_name', text="")
		row.prop(self, 'name_suffix', toggle=True)
		box.prop(self, 'use_obj_props')
		box.prop(self, 'save_log')


#---------------------------------------

def menu_import(self, context):
	self.layout.operator(Import_GMDC.bl_idname, text="GMDC (.gmdc, .5gd)")

def menu_export(self, context):
	self.layout.operator(Export_GMDC.bl_idname, text="GMDC (.gmdc)")

classes = (
	Import_GMDC,
	Export_GMDC,
)

def register():
	from bpy.utils import register_class
	for cls in classes:
		register_class(cls)
	bpy.types.TOPBAR_MT_file_import.append(menu_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_export)

def unregister():
	from bpy.utils import unregister_class
	for cls in classes:
		unregister_class(cls)
	bpy.types.TOPBAR_MT_file_import.remove(menu_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_export)

if __name__ == "__main__":
	register()
