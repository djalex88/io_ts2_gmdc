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

import bpy
from itertools import chain
from mathutils import Vector as BlenderVector
from .gmdc_tools import (
	log,
	error,
	set_log_file,
	close_log_file,
	print_last_exception,
	load_resource,
	Vector,
	Transform,
	build_transform_tree
	)

def popup_message(title, message, icon='NONE'):
	bpy.context.window_manager.popup_menu(lambda w, c: w.layout.label(text=message), title, icon)


########################################
##  Importer
########################################

def begin_import(filename, scene, settings):

	from os.path import basename

	mode = settings['import_mode']

	if not basename(filename):
		popup_message("Error!", "No file selected!", 'ERROR')
		return

	# create log file (if needed)
	if settings['save_log']:
		s = filename + '.import_log.txt'
		log( 'Opening log file "%s" for writing... ' % s )
		try:
			f = open(s, 'w')
		except IOError as e:
			error(e)
			popup_message("Error!", "Could not open log file for writing.", 'ERROR')
			return
		# Ok
		set_log_file(f)

	#
	# begin import
	#

	log( '########################################' )
	log( '##  TS2 GMDC Importer                 ##' )
	log( '########################################' )
	log( 'File:', filename )
	log( 'Mode:', mode )
	log( 'Settings:' )
	if mode == 'GEOMETRY':
		log( '--Import bounding geometry:  ', settings['import_bmesh'] )
		log( '--Remove doubles:            ', settings['remove_doubles'] )
		log( '--Replace inverse transforms:', settings['replace_inv_t'] )
	else:
		assert mode == 'SKELETON'
		log( '--Only for selected objects: ', settings['selected_only'] )
		log( '--Import all bones:          ', settings['all_bones'] )
	log()

	# load resource
	log( 'Opening file "%s"...' % filename )
	try:
		res = load_resource(filename, settings['save_log'] and 2 or 1)
	except:
		print_last_exception()
		res = False
	if mode == 'GEOMETRY':
		if not res or not res.nodes or res.nodes[0].type != 'cGeometryDataContainer':
			res and error( 'Error! Not a GMDC file!' )
			close_log_file()
			popup_message("Error!", "Could not load geometry file. See log for details.", 'ERROR')
			return
	else: #### 'SKELETON'
		if not res or not res.nodes or res.nodes[0].type != 'cResourceNode':
			res and error( 'Error! Not a CRES file!' )
			close_log_file()
			popup_message("Error!", "Could not load resource node file. See log for details.", 'ERROR')
			return
	log()

	try:
		if mode == 'GEOMETRY':
			geometry = res.nodes[0].geometry
			if settings['remove_doubles']:
				log( 'Removing doubles...' )
				geometry.remove_doubles()
				log()
			import_geometry(scene, geometry, settings)

		else: #### 'SKELETON'
			transform_tree = build_transform_tree(res.nodes)
			if not import_skeleton(scene, transform_tree, settings):
				raise Exception()

	except:
		print_last_exception()
		popup_message("Error!", "An error has occured. See log for details.", 'ERROR')

	else:
		popup_message("Done!", "See console for more info.", 'INFO')

	finally:
		close_log_file()


#---------------------------------------

def import_geometry(scene, geometry, settings):

	def create_mesh(name, V, I, T1, T2):

		# create mesh
		#
		mesh = bpy.data.meshes.new(name)

		mesh.from_pydata(V, [], I)
		mesh.validate(verbose=True)

		for poly in mesh.polygons:
			poly.use_smooth = True

		if T1:
			# add new texture layer
			uv_layer = mesh.uv_layers.new()
			for poly, t in zip(mesh.polygons, T1):
				for loop_idx, (u, v) in zip(poly.loop_indices, t):
					uv_layer.data[loop_idx].uv = (u, 1-v) # Direct3D -> OpenGL

			if T2:
				uv_layer = mesh.uv_layers.new()
				for poly, t in zip(mesh.polygons, T2):
					for loop_idx, (u, v) in zip(poly.loop_indices, t):
						uv_layer.data[loop_idx].uv = (u, 1-v)

		return mesh


	active_collection_objects = bpy.context.view_layer.active_layer_collection.collection.objects

	# deselect all objects in the scene (if any)
	#
	if bpy.ops.object.mode_set.poll():
		bpy.ops.object.mode_set(mode='OBJECT')
	for obj in active_collection_objects:
		obj.select_set(False)
	bpy.context.view_layer.objects.active = None

	log( 'Creating mesh objects...' )

	#
	# add mesh objects (main geometry)
	#

	for group in geometry.index_groups:

		log( 'Index group "%s"' % group.name )

		data_group = geometry.data_groups[group.data_group_index]

		# define index mapping { old_index -> new_index }
		S = {x : i for i, x in enumerate(sorted(set(chain(*group.indices))))}

		# map indices
		I = [(S[i], S[j], S[k]) for i, j, k in group.indices]

		# filtering function
		def select_data(data):
			return [x for i, x in enumerate(data) if i in S]

		V = select_data(data_group.vertices)

		# texture coords
		if data_group.tex_coords:
			T1 = select_data(data_group.tex_coords)
			T1 = [(T1[i], T1[j], T1[k]) for i, j, k in I]
			if data_group.tex_coords2:
				T2 = select_data(data_group.tex_coords2)
				T2 = [(T2[i], T2[j], T2[k]) for i, j, k in I]
			else:
				T2 = None
		else:
			T1 = group.tex_coords and group.tex_coords[:] # copy or None
			T2 = group.tex_coords2 and group.tex_coords2[:]

		# remove degenerate geometry,
		# i.e., triangles with less than 3 different indices, duplicate triangles
		#
		w = [] ; s = {}
		for i, tri in enumerate(tuple(sorted(tri)) for tri in I):
			if len(set(tri)) < 3:
				w.append(i)
				log( '--Triangle # %i' % i, tri, 'removed' )
			else:
				idx = s.setdefault(tri, i)
				if idx != i:
					log( '--Duplicate triangle # %i (same as %i)' % (i, idx), tri, 'removed' )
					w.append(i)
		for i in reversed(w):
			del I[i]
			if T1:
				del T1[i]
				if T2:
					del T2[i]
		del w, s

		log( '--Creating mesh object (vertices: %i, triangles: %i)...' % (len(V), len(I)) )

		# create mesh and add it to the collection
		#
		mesh = create_mesh(group.name, V, I, T1, T2)
		obj = bpy.data.objects.new(group.name, mesh)
		active_collection_objects.link(obj)

		# save original name and flags
		obj['name'] = group.name
		obj['flags'] = "%08X" % group.flags

		obj.select_set(True)

		log( '--Rigging:', data_group.bones and 'yes' or 'no' )

		# rigging
		#
		if data_group.bones:

			B = select_data(data_group.bones)
			W = select_data(data_group.weights)

			log( '--Assigning vertices to vertex groups...' )

			# add vertex groups (global indices)
			for idx in group.bones:
				obj.vertex_groups.new(name=f"bone#{idx}")

			# assign vertices to groups
			for i, (bones, weights) in enumerate(zip(B, W)):
				for j, bone_idx in enumerate(bones):
					if j == 3:
						w = 1.0 - sum(weights)
					else:
						w = weights[j]
					obj.vertex_groups[bone_idx].add([i], w, 'REPLACE')

		# shape keys
		#
		if data_group.keys:

			log( '--Adding shape keys...' )

			keys = select_data(data_group.keys)
			dV = list(map(select_data, data_group.dVerts))

			log( '\x20\x20--Length of dV: (%i, %i, %i, %i)' % tuple(map(len, dV)) )

			# basis
			obj.shape_key_add(name="Basis")

			for morph_idx, name in enumerate(geometry.morph_names):

				used_keys = list(filter(lambda t: morph_idx in t[1], enumerate(keys)))
				if used_keys:

					name = "::".join(name)

					log( '\x20\x20--Key "%s"' % name )

					block_verts = obj.shape_key_add(name=name).data

					# modify mesh with dV
					#
					for i, key in used_keys:
						j = key.index(morph_idx)
						v = dV[j]
						if v:
							block_verts[i].co+= BlenderVector(v[i])

					del used_keys

	#<- groups

	#
	# add bounding geometry
	#

	if settings['import_bmesh']:

		if geometry.static_bmesh:

			log( 'Creating static bounding mesh...' )

			V, I = geometry.static_bmesh

			mesh = bpy.data.meshes.new("b_mesh")
			mesh.from_pydata(vertices=V, edges=[], faces=I)
			mesh.validate(verbose=False)

			obj = bpy.data.objects.new("b_mesh", mesh)
			active_collection_objects.link(obj)
			obj.select_set(True)

		if geometry.dynamic_bmesh:

			log( 'Creating dynamic bounding mesh...' )

			# collect all parts, transform vertices, update triangle indices
			#
			V_all = []
			I_all = []
			S_all = []
			for idx, part in enumerate(geometry.dynamic_bmesh):
				if part:
					V, I = part

					# remove all degenerate triangles
					I = list(filter(lambda tri: len(set(tri))==3, I))

					# compute subset of vertex indices for this part
					j = len(V_all)
					S = {x : i+j for i, x in enumerate(sorted(set(chain(*I))))}

					# compute transform into Object Space
					rot, loc = geometry.inverse_transforms[idx]
					t = Transform(loc, rot).get_inverse()

					# transform vertices and map triangles indices
					V_all += [t.transformPoint(Vector(*x)).to_tuple() for i, x in enumerate(V) if i in S]
					I_all += [(S[i], S[j], S[k]) for i, j, k in I]
					S_all.append(S)
				else:
					S_all.append(None)

			# create mesh
			mesh = bpy.data.meshes.new("b_mesh")
			mesh.from_pydata(vertices=V_all, edges=[], faces=I_all)
			mesh.validate(verbose=False)

			obj = bpy.data.objects.new("b_mesh", mesh)
			active_collection_objects.link(obj)
			obj.select_set(True)

			# add vertex groups
			for idx, S in enumerate(S_all):
				if S:
					obj.vertex_groups.new(name=f"bone#{idx}").add(list(S.values()), 1.0, 'REPLACE')

			del V_all, I_all, S_all

	#<- b_mesh

	#
	# load inverse transforms (if any)
	#

	if geometry.inverse_transforms:

		inverse_transforms = tuple(geometry.inverse_transforms)

		inverse_transforms_saved = None

		try:
			w = tuple( (tuple(rot), tuple(loc)) for rot, loc in bpy.context.scene['gmdc_inverse_transforms'] ) or None
			log( 'Scene already has inverse transforms (%i)' % len(w) )
			if inverse_transforms != inverse_transforms_saved and settings['replace_inv_t']:
				raise
		except:
			if inverse_transforms_saved:
				log( '--Replacing inverse transforms...' )
			else:
				log( 'Saving inverse transforms in scene["gmdc_inverse_transforms"]...' )
			bpy.context.scene['gmdc_inverse_transforms'] = inverse_transforms

	log( 'Finished!' )

	return True


#---------------------------------------

def import_skeleton(scene, transform_tree, settings):

	active_collection_objects = bpy.context.view_layer.active_layer_collection.collection.objects

	#
	# obtain list of meshes and compute index set of used bones
	#

	bone_set = set()

	if settings['selected_only']:
		mesh_object_filter = lambda obj: obj.type=='MESH' and obj.select_get()
	else:
		mesh_object_filter = lambda obj: obj.type=='MESH'

	mesh_objects = list(filter(mesh_object_filter, active_collection_objects))

	for obj in mesh_objects:
		for vert_group in obj.vertex_groups:
			parts = vert_group.name.split("#")
			try:
				bone_idx = int(parts[-1])
				bone_name = transform_tree.get_node(bone_idx).name
			except ValueError:
				error( "Error! Could not extract bone index from group name '%s'." % vert_group.name )
				return False
			except KeyError:
				error( "Error! No bone with index %i." % bone_idx )
				return False
			else:
				# rename vertex group
				vert_group.name = bone_name + "#" + str(bone_idx)
				# include to set
				bone_set.add(bone_idx)

	#
	# compute set of nodes to build the armature from
	#

	if settings['all_bones']:

		node_ids = set(map(id, transform_tree))

	else:
		node_ids = set()
		for j in bone_set:
			node = transform_tree.get_node(j)
			assert not isinstance(node, tuple)

			# include all nodes down to root
			while node and id(node) not in node_ids:
				node_ids.add(id(node))
				node = node.parent

	#---------------------------------------
	# helpers

	def make_unique_bone_name(name, idx, collection):
		idx = f"#{idx}" if idx!=None else ""
		s = name + idx
		i = 1
		while s in collection:
			s = name + f".{i}" + idx
			i+= 1
		return s

	def add_bones_to_armature(transform_nodes, parent_bone=None):

		for node in transform_nodes:
			if id(node) in node_ids:

				name = make_unique_bone_name(node.name, node.bone_index, armature.edit_bones.keys())

				bone = armature.edit_bones.new(name)
				bone.head = node.abs_transform.loc.to_tuple()

				# compute tail pos as arithmetic mean
				child_node_locations = []
				for c_node in node.child_nodes:
					if id(c_node) in node_ids and c_node.bone_index in bone_set:
						child_node_locations.append(c_node.abs_transform.loc)
				if child_node_locations and node.bone_index in bone_set:
					tail = sum(child_node_locations, Vector()) * (1.0/len(child_node_locations))
				else:
					tail = node.abs_transform.loc

				# the bone's length must not be 0, otherwise Blender ignores it
				if (node.abs_transform.loc - tail).len() < 0.025:
					tail = node.abs_transform.loc + node.abs_transform.rot.get_matrix().col(2)*0.05
				bone.tail = tail.to_tuple()

				if parent_bone:
					bone.parent = parent_bone

				# add children
				add_bones_to_armature(node.child_nodes, bone)

	#
	# create armature object and add armature modifier(s)
	#

	if node_ids:

		if bpy.ops.object.mode_set.poll():
			bpy.ops.object.mode_set(mode='OBJECT')

		log( 'Creating armature...' )
		log( '--Number of bones (%i)' % len(node_ids) )

		# create new armature object
		#
		armature = bpy.data.armatures.new(name="Armature")
		armature.display_type = 'STICK'

		armature_object = bpy.data.objects.new("Armature", armature)
		armature_object.show_in_front = True
		active_collection_objects.link(armature_object)
		armature_object.select_set(True)

		# activate armature object and enter edit mode
		#
		bpy.context.view_layer.objects.active = armature_object
		assert bpy.ops.object.mode_set.poll()
		bpy.ops.object.mode_set(mode='EDIT')

		# add bones and return back to object mode
		#
		add_bones_to_armature(transform_tree.root_nodes)
		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.context.view_layer.objects.active = None

		log( '--Adding armature modifier(s)...' )

		for obj in mesh_objects:
			modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
			modifier.object = armature_object
			modifier.use_vertex_groups = True

		log( 'Finished!' )

	else:

		log( 'No bones. No armature object created.' )

	return True


