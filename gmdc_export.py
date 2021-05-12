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
from struct import pack
from itertools import chain, repeat
from mathutils import Vector as BlenderVector
from .gmdc_tools import (
	log,
	error,
	set_log_file,
	close_log_file,
	print_last_exception,
	chunk,
	to_hex,
	DataGroup,
	IndexGroup,
	GeometryData,
	create_gmdc_file,
	Vector,
	Transform
	)

def popup_message(title, message, icon='NONE'):
	bpy.context.window_manager.popup_menu(lambda w, c: w.layout.label(text=message), title, icon)


########################################
##  Exporter
########################################

def begin_export(filename, scene, settings):

	from os.path import basename

	if not basename(filename):
		popup_message("Error!", "No file selected!", 'ERROR')
		return

	if settings['export_bmesh'] and not settings['bmesh_name']:
		popup_message("Error!", "Enter bounding mesh\'s object name.", 'ERROR')
		return

	# create log file (if needed)
	if settings['save_log']:
		s = filename + '.export_log.txt'
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
	# begin export
	#

	log( '########################################' )
	log( '##  TS2 GMDC Exporter                 ##' )
	log( '########################################' )
	log( 'File:', filename )
	log( 'Settings:' )
	log( '--Only selected objects:', settings['selected_only'] )
	log( '--Apply transforms:', settings['apply_transforms'] )
	log( '--Export rigging:  ', settings['export_rigging'] )
	log( '--Export tangents: ', settings['export_tangents'] )
	log( '--Export bounding geometry:', settings['export_bmesh'] )
	log( '--Bounding mesh name:', settings['bmesh_name'] and '"%s"' % settings['bmesh_name'] or 'none' )
	log( '--Weight threshold:', settings['bmesh_threshold'] )
	log( '--Export morphs:', settings['export_morphs'] )
	log( '--Resource name:', settings['resource_name'] and '"%s"' % settings['resource_name'] or 'none' )
	log( '--Name suffix:  ', settings['name_suffix'] )
	log( '--Use properties: ', settings['use_obj_props'] )
	log()

	resource_name = settings['resource_name']
	if not resource_name:
		resource_name = basename(filename).split(".")
		resource_name = ".".join(resource_name[:-1] or resource_name)
	if settings['name_suffix']:
		resource_name+= '_tslocator_gmdc'

	log( 'Preparing geometry...' )
	geometry = None
	try:
		geometry = export_geometry(scene, settings)
	except:
		print_last_exception()
	if not geometry:
		popup_message("Error!", "An error has occured while preparing geometry. See log for details.", 'ERROR')
		close_log_file()
		return

	log()
	log( 'Creating GMDC file "%s"... ' % filename )
	try:
		create_gmdc_file(filename, resource_name, geometry)

	except:
		print_last_exception()
		popup_message("Error!", "An error has occured while creating GMDC file. See log for details.", 'ERROR')

	else:
		# Ok
		log( 'Finished!' )
		popup_message("Done!", "See console for more info.", 'INFO')

	finally:
		close_log_file()


#---------------------------------------

def export_geometry(scene, settings):

	if bpy.ops.object.mode_set.poll():
		bpy.ops.object.mode_set(mode='OBJECT')

	active_collection_objects = bpy.context.view_layer.active_layer_collection.collection.objects

	# get all mesh objects
	#
	if settings['selected_only']:
		mesh_object_filter = lambda obj: obj.type=='MESH' and obj.select_get()
	else:
		mesh_object_filter = lambda obj: obj.type=='MESH'

	mesh_objects = list(filter(mesh_object_filter, active_collection_objects))

	# apply transforms if needed
	#
	if settings['apply_transforms']:
		for obj in mesh_objects:
			obj.select_set(True)
		if bpy.ops.object.transform_apply.poll():
			bpy.ops.object.transform_apply(rotation=True, scale=True, location=False, properties=False)

	# check whether visual transforms applied
	#
	objects = [obj for obj in mesh_objects if tuple(obj.rotation_euler)!=(0, 0, 0) or tuple(obj.scale)!=(1, 1, 1)]
	if objects:
		error( 'Error! The following mesh ' + ('objects have' if len(objects)>1 else 'object has') + ' non-applied visual transforms:' )
		for obj in objects:
			error( '\x20\x20%s -> rot: %s, size: %s' % (str(obj), str(obj.rotation_euler), str(obj.scale)) )
		error( 'Solution: apply visual transforms (Ctrl+A).' )
		return False

	# bounding mesh object
	#
	if settings['export_bmesh']:
		bmesh_object = active_collection_objects.get(settings['bmesh_name'])
		if not bmesh_object or bmesh_object.type != 'MESH':
			error( 'Error! Could not find bounding mesh.' )
			return False
		# remove from objects
		if mesh_objects.count(bmesh_object):
			mesh_objects.remove(bmesh_object)

	# check that object list is not empty
	if not mesh_objects:
		error( 'Error! Object list is empty.' )
		return False

	# inverse transforms
	#
	if settings['export_rigging']:
		try:
			inverse_transforms = tuple( (tuple(rot), tuple(loc)) for rot, loc in bpy.context.scene['gmdc_inverse_transforms'] )
		except:
			error( 'Error! No inverse transforms. (scene["gmdc_inverse_transforms"] is not defined.)' )
			return False
	else:
		inverse_transforms = None

	#
	# process main geometry
	#

	DATA_GROUPS = [] ; INDEX_GROUPS = []

	MORPH_NAMES = [] # [index] -> name

	log( 'Main geometry' )

	for obj in mesh_objects:

		log( str(obj) )

		# initial rigging state for current mesh
		#
		rigging = settings['export_rigging']

		# activate current object and shape key
		bpy.context.view_layer.objects.active = obj
		obj.active_shape_key_index = 0
		for i in range(2): bpy.ops.object.editmode_toggle()

		mesh = obj.data

		mesh.calc_loop_triangles()

		obj_loc = obj.location

		if len(mesh.polygons) == 0:
			error( 'Error! Mesh object has no faces.' )
			return False

		# texture coords
		#
		mesh_tex_coords = []
		if not mesh.uv_layers:
			error( 'Error! Mesh object has no UV layer.' )
			return False
		elif len(mesh.uv_layers) == 1:
			uv_layer1 = mesh.uv_layers[0]
			for tri in mesh.loop_triangles:
				tri_uv = []
				for loop_idx in tri.loops:
					u, v = uv_layer1.data[loop_idx].uv
					tri_uv.append((u, 1-v)) # OpenGL -> Direct3D
				mesh_tex_coords.append(tri_uv)
		else:
			# two UV layers
			uv_layer1, uv_layer2 = mesh.uv_layers[:2]
			for tri in mesh.loop_triangles:
				tri_uv = []
				for loop_idx in tri.loops:
					u1, v1 = uv_layer1.data[loop_idx].uv
					u2, v2 = uv_layer1.data[loop_idx].uv
					tri_uv.append(((u1, 1-v1), (u2, 1-v2)))
				mesh_tex_coords.append(tri_uv)

		# tangents
		#
		if settings['export_tangents']:
			mesh.calc_tangents(uvmap=uv_layer1.name)
			mesh_tangents = []
			for tri in mesh.loop_triangles:
				tri_tan = []
				for loop_idx in tri.loops:
					tri_tan.append(tuple(mesh.loops[loop_idx].tangent))
				mesh_tangents.append(tri_tan)
		else:
			mesh_tangents = repeat((None, None, None)) # no tangents

		if rigging:
			# get group and weight lists for every vertex
			# then compute mapping function

			vertex_influences = [(*zip(*((g.group, g.weight) for g in v.groups if g.weight > 0)),) for v in mesh.vertices]

			vertex_group_index_map = {} # { vertex_group_index -> (bone_idx, idx_type) }

			bone_indices = [] # [index] -> global_bone_indices

			for group in obj.vertex_groups:
				# get bone index
				s = group.name.split("#")
				try:
					bone_idx = int(s[-1])
					if len(s) < 2 or bone_idx < 0:
						raise Exception()
				except:
					error( 'Error! Could not extract bone index from vertex group name "%s".' % name )
					return False
				if bone_idx in bone_indices:
					error( 'Error! Duplicate bone index (%i) within vertex group names detected.' % bone_idx )
					return False
				vertex_group_index_map[group.index] = (bone_idx, 'global')
				bone_indices.append(bone_idx)

			bone_indices = []

			def map_group_indices(group_indices):
				mapped_indices = []
				for idx in group_indices:
					bone_idx, idx_type = vertex_group_index_map[idx]
					if idx_type == 'global':
						# new local index
						# append bone_idx into global bone index list
						local_bone_idx = len(bone_indices)
						bone_indices.append(bone_idx)
						# replace global with local index
						vertex_group_index_map[idx] = (local_bone_idx, 'local')
						mapped_indices.append(local_bone_idx)
					else:
						mapped_indices.append(bone_idx)
				return tuple(mapped_indices)

		all_vertices = [] # for non-indexed vertices

		for tri, tri_uv, tri_tan in zip(mesh.loop_triangles, mesh_tex_coords, mesh_tangents):
			verts = []
			norms = []
			for idx in tri.vertices:
				verts.append(tuple(mesh.vertices[idx].co + obj_loc))
				norms.append(tuple(mesh.vertices[idx].normal))
			if rigging:
				bones = []
				weights = []
				for idx in tri.vertices:
					g, w = vertex_influences[idx]
					if len(g) > 4:
						error( 'Error! Vertex # %i of mesh object "%s" is in more that 4 vertex groups.' % (idx, obj.name) )
						return False
					# normalize weights and add to list
					f = sum(w)
					if f > 0.0001:
						bones.append(map_group_indices(g))
						weights.append(tuple(x/f for x in w))
					else:
						bones.append(tuple())
						weights.append(tuple())
			else:
				bones   = [(), (), ()]
				weights = [(), (), ()]

			# add vertices to list
			all_vertices.extend(zip(verts, norms, tri_uv, bones, weights, tri_tan))

		#<- triangles

		del mesh_tex_coords, mesh_tangents

		#
		# morphs / vertex animations
		#

		if settings['export_morphs'] and mesh.shape_keys and len(mesh.shape_keys.key_blocks) > 1:
			# 0 - None
			# 1 - diff in verts
			# 2 - diff in verts and norms
			morphing = settings['export_morphs']
		else:
			morphing = False

		if morphing:

			log( '--Processing shape keys...' )

			mesh_morphs = [] # morph indices of current mesh object
			first_new_morph_index = None # first new morph that is not present in MORPH_NAMES

			dVerts = []
			dNorms = []

			# compute differences

			for key_idx, key_block in enumerate(mesh.shape_keys.key_blocks[1:], 1): # skip Basis key

				name = tuple(key_block.name.strip().split('::'))
				if len(name) != 2:
					error( 'Error! Invalid morph name: "%s"' % '::'.join(name) )
					return False

				if name in MORPH_NAMES:
					j = MORPH_NAMES.index(name)
				else:
					# new morph
					j = len(MORPH_NAMES)
					MORPH_NAMES.append(name)
					if first_new_morph_index == None:
						first_new_morph_index = j
				mesh_morphs.append(j)

				log( '\x20\x20--Key "%s" (%i)' % (name, key_idx) )

				# activate morph
				obj.active_shape_key_index = key_idx
				assert bpy.ops.object.editmode_toggle.poll()
				for i in range(2): bpy.ops.object.editmode_toggle()

				mesh.calc_loop_triangles()

				if settings['export_tangents'] and morphing == 2:
					mesh.calc_tangents(uvmap=uv_layer1.name)

				# add difference arrays
				dv = [] ; dVerts.append(dv)
				dn = [] ; dNorms.append(dn)

				# loop through all triangles and compute vertex differences
				j = 0
				for tri in mesh.loop_triangles:
					verts = [(key_block.data[idx].co + obj_loc) for idx in tri.vertices]
					norms = [mesh.vertices[idx].normal for idx in tri.vertices]

					for co, no in zip(verts, norms):
						dv.append(tuple(co - BlenderVector(all_vertices[j][0])))
						dn.append(tuple(no - BlenderVector(all_vertices[j][1])))
						j+= 1
				assert j == len(all_vertices)

			log( '\x20\x20--Packing...' )

			keys = [[] for i in range(len(all_vertices))]

			if morphing == 2: # vertices and normals
				packed_dv = [[] for i in range(len(all_vertices))]
				packed_dn = [[] for i in range(len(all_vertices))]

				# loop through all difference arrays (morphs)
				# select only affected vertices
				for i, dv, dn in zip(mesh_morphs, dVerts, dNorms):
					for co, no, key, pdv, pdn in zip(dv, dn, keys, packed_dv, packed_dn):
						if co != (0.0, 0.0, 0.0) or no != (0.0, 0.0, 0.0): # vertex affected
							if len(key) == 4:
								error( 'Error! Some vertices are affected by more than 4 morphs (shape keys).' )
								return False
							# morph index
							key.append(i)
							# difference
							pdv.append(co)
							pdn.append(no)
				# replaced with packed arrays
				dVerts = packed_dv
				dNorms = packed_dn

				del packed_dv, packed_dn

			else: # vertices only
				packed_dv = [[] for i in range(len(all_vertices))]

				for i, dv in zip(mesh_morphs, dVerts):
					for co, key, pdv in zip(dv, keys, packed_dv):
						if co != (0.0, 0.0, 0.0):
							if len(key) == 4:
								error( 'Error! Some vertices are affected by more than 4 morphs (shape keys).' )
								return False
							# morph index
							key.append(i)
							# difference
							pdv.append(co)
				dVerts = packed_dv

				del packed_dv

			assert len(dVerts) == len(all_vertices)

			if not any(keys):
				log( '\x20\x20--Differences between shape keys of mesh object "%s" were not detected.' % obj.name )
				morphing = False
				if first_new_morph_index != None:
					del MORPH_NAMES[first_new_morph_index : ] # remove newly added morph names

			else:
				keys = map(tuple, keys)

				num_arrays = max(len(v) for v in dVerts) # number of difference arrays
				log( '\x20\x20--Number of arrays:', num_arrays )

				# align arrays by padding with (0.0, 0.0, 0.0)

				dVerts = [(tuple(dv) + ((0.0, 0.0, 0.0),)*4)[:num_arrays] for dv in dVerts]

				if morphing == 2:
					dNorms = [(tuple(dn) + ((0.0, 0.0, 0.0),)*4)[:num_arrays] for dn in dNorms]
					for i, (key, dv, dn) in enumerate(zip(keys, dVerts, dNorms)):
						all_vertices[i]+= (key, dv, dn)
				else:
					for i, (key, dv) in enumerate(zip(keys, dVerts)):
						all_vertices[i]+= (key, dv)

			del keys, dVerts, dNorms

		#<- morphing

		#
		# index geometry
		#

		log( '--Indexing geometry...' )

		unique_verts = {} # { vertex -> index }
		indices = []

		for vertex in all_vertices:
			k = unique_verts.setdefault(vertex, len(unique_verts))
			indices.append(k)

		unique_verts = [v for v, i in sorted(unique_verts.items(), key=lambda x: x[1])]

		log( '\x20\x20--Vertex count: %i -> %i' % (len(all_vertices), len(unique_verts)) )

		del all_vertices

		V, N, T, B, W, X, K, dV, dN = [*map(list, zip(*unique_verts))] + [None for i in range(3-2*morphing)]

		# separate uv layers (if needed)
		if len(mesh.uv_layers) > 1:
			T1, T2 = zip(*T)
		else:
			T1 = T
			T2 = None

		del unique_verts, T

		#
		# add new data group or extend an existing one
		#

		# does the mesh have rigging data ?
		rigging = rigging and any(B)

		# try to find a suitable data group
		group = None
		for i, g in enumerate(DATA_GROUPS):
			b1 = (bool(g.bones) == rigging) # same rigging state
			if morphing:
				b2 = sum(bool(x) for x in g.dVerts) == len(dV[0]) # same number of difference arrays
			else:
				b2 = not bool(g.dVerts[0]) # no difference arrays
			b3 = (bool(g.tex_coords2) == bool(T2)) # presence of additional UV layer
			if b1 and b2 and b3:
				# found
				ref_group, group = i, g
				break
		if group:
			k = group.count
			indices = list(map(lambda x: x+k, indices)) # shift indices
			log( '--Extending group # %i...' % ref_group )
		else:
			ref_group = len(DATA_GROUPS)
			group = DataGroup() ; DATA_GROUPS.append(group)
			log( '--Adding new group # %i...' % ref_group )

		# add vertices to group
		#
		group.vertices.extend(V)
		group.normals.extend(N)
		group.tex_coords.extend(T1)
		if T2:
			group.tex_coords2.extend(T2)
		if rigging:
			group.bones.extend(B)
			group.weights.extend(W)
		if settings['export_tangents']:
			group.tangents.extend(X)
		if morphing:
			group.keys.extend(K)
			dV = [*map(list, zip(*dV)), [], [], []]
			for v, w in zip(group.dVerts, dV):
				v.extend(w)
			if morphing > 1:
				dN = [*map(list, zip(*dN)), [], [], []]
				for v, w in zip(group.dNorms, dV):
					v.extend(w)

		del V, N, T1, T2, B, W, X, K, dV, dN

		k = group.count
		group.count = len(group.vertices)
		log( '\x20\x20--Vertex count:', '%i -> %i' % (k, group.count) if k else group.count )

		#
		# create index group
		#

		# name
		name = obj.name
		if settings['use_obj_props']:
			x = obj.get('name')
			if x is not None:
				if type(x) != str or x.strip() == "":
					log( 'Warning! Invalid data for property "name". Ignored.' )
				else:
					name = x.strip()

		log( '--Creating new index group # %i, "%s" (triangles: %i)...' % (len(INDEX_GROUPS), name, len(indices)/3) )

		group = IndexGroup(name) ; INDEX_GROUPS.append(group)
		group.data_group_index = ref_group
		group.indices = chunk(tuple(indices), 3) # triangles

		del indices

		# flags
		if settings['use_obj_props']:
			x = obj.get('flags')
			if x:
				try:
					if type(x) == str:
						x = int(x, 16)
					elif type(x) != int:
						raise TypeError()
					log( '--Flags:', to_hex(pack('<L', x)) )
				except TypeError:
					x = None
					log( 'Warning! Invalid data for property "flags". Ignored.' )
				else:
					group.flags = x

		# bone index mapping
		if rigging:
			# check global bone indices
			for bone_idx in bone_indices:
				if bone_idx >= len(inverse_transforms):
					error( 'Error! No inverse transform for bone # %i.' % bone_idx )
					return False
			# ok
			group.bones = bone_indices

			del bone_indices

	#<- mesh_objects

	#
	# bounding geometry
	#

	static_bmesh = None ; dynamic_bmesh = None

	if settings['export_bmesh']:

		bmesh_object = active_collection_objects.get(settings['bmesh_name'])
		if not bmesh_object:
			error( 'Error! Could not find bounding mesh object with name "%s".' % settings['bmesh_name'] )
			return False

		mesh = bmesh_object.data

		mesh.calc_loop_triangles()

		obj_loc = obj.location

		log( 'Bounding mesh object %s:' % bmesh_object )

		if settings['export_rigging']:

			dynamic_bmesh = []

			# create bone index map
			#
			bone_vertex_groups = {} # { bone_idx -> group_idx }

			for group in bmesh_object.vertex_groups:
				# get bone index
				name = group.name
				s = name.split("#")
				try:
					bone_idx = int(s[-1])
					if len(s) < 2 or idx < 0:
						raise Exception()
				except:
					error( 'Error! Could not extract bone index from vertex group name "%s".' % name )
					return False
				if bone_idx in bone_vertex_groups:
					error( 'Error! Duplicate bone index (%i) within vertex group names detected.' % bone_idx )
					return False
				bone_vertex_groups[bone_idx] = group.index

			threshold = settings['bmesh_threshold']

			for bone_idx in range(max(bone_vertex_groups) + 1):

				group_idx = bone_vertex_groups.get(bone_idx)

				if group_idx is not None:

					I = []

					vertex_index_map = {} # { global_index -> local_index }

					vertex_influences = [(tuple(g.group for g in v.groups), tuple(g.weight for g in v.groups)) for v in mesh.vertices]

					for tri in mesh.loop_triangles:
						# calculate the average weight over the vertices
						sum_w = 0
						for i, idx in enumerate(tri.vertices):
							groups, weights = vertex_influences[idx]
							if group_idx in groups:
								sum_w+= weights[groups.index(group_idx)]
						if sum_w/3 >= threshold:
							# the triangle is affected
							indices = []
							for idx in tri.vertices:
								k = len(vertex_index_map)
								indices.append(vertex_index_map.setdefault(idx, k))
							I.append(tuple(indices))

					if vertex_index_map:

						# get inverse transform
						#
						if bone_idx >= len(inverse_transforms):
							error( 'Error! No inverse transform for bone # %i.' % bone_idx )
							return False

						rot, loc = inverse_transforms[bone_idx]
						t = Transform(loc, rot)

						# sort by local index
						vertex_index_map = sorted(vertex_index_map.items(), key=lambda x: x[1])

						V = []

						# transform coord into bone space
						for i, j in vertex_index_map:
							a = mesh.vertices[i].co + obj_loc
							a = t.transformPoint( Vector(a.x, a.y, a.z) ).to_tuple()
							V.append(a)

						dynamic_bmesh.append((V, I))
						log( '--Part # %02i -> vertices: %i, triangles: %i' % (bone_idx, len(V), len(I)) )

					else:
						dynamic_bmesh.append(None)

				else:
					dynamic_bmesh.append(None)

			if not any(dynamic_bmesh):
				dynamic_bmesh = None

		else: # static

			V = [tuple(v.co + obj_loc) for v in mesh.vertices]
			I = [tuple(tri.vertices) for tri in mesh.loop_triangles]

			static_bmesh = (V, I)

			log( '--Static bounding mesh -> vertices: %i, triangles: %i' % (len(V), len(I)) )

	#
	# normals
	#

	if settings['align_normals'] and settings['align_target']:
		from .gmdc_tools import load_resource
		try:
			g = load_resource(settings['align_target'], log_level=0).nodes[0].geometry
			verts = g.data_groups[0].vertices
			norms = g.data_groups[0].normals
		except:
			error( 'Error! Could not load data from file "%s".' % settings['align_target'] )
		else:
			# create vertex map { vertex -> normal }
			vertex_map = dict(zip(verts, norms))

			# match vertices and replace normals
			log( 'Aligning normals...' )
			log( 'Target:', settings['align_target'] )
			count = 0
			for group_idx, group in enumerate(DATA_GROUPS):
				log( '--Data group # %i' % group_idx )
				for i, vertex in enumerate(group.vertices):
					normal = vertex_map.get(vertex)
					if normal:
						log( '\x20\x20--Vertex # %i' % i )
						group.normals[i] = normal
						count+= 1
			log( '--Replaced %i normals' % count )

	return GeometryData(DATA_GROUPS, INDEX_GROUPS, inverse_transforms, MORPH_NAMES, static_bmesh, dynamic_bmesh)


