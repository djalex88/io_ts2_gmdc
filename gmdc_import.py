#!BPY

"""
Name: 'GMDC (.gmdc, .5gd)'
Blender: 249
Group: 'Import'
Tooltip: 'Import TS2 GMDC file' """

#-------------------------------------------------------------------------------
# Copyright (C) 2016  DjAlex88 (https://github.com/djalex88/)
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

from gmdc_tools import *
from itertools import chain

import bpy, Blender
from Blender import Draw
from Blender.Mathutils import Vector as BlenderVector

########################################
##  Importer
########################################

def create_objects(geometry, transform_tree, settings):

	#---------------------------------------
	# subroutines

	def create_mesh(name, V, I, T):

		# create mesh
		#
		mesh = Blender.Mesh.New(name)

		mesh.verts.extend(V)
		mesh.faces.extend(I, ignoreDups=True, smooth=True)

		# since Blender recalculates normals, setting original normals is useless
		# instead, calculate normals
		mesh.calcNormals()

		if T:
			# assign texture coords
			#
			for f, t in zip(mesh.faces, T):
				uv1, uv2, uv3 = t
				# Direct3D -> OpenGL
				u, v = uv1 ; uv1 = BlenderVector(u, 1-v)
				u, v = uv2 ; uv2 = BlenderVector(u, 1-v)
				u, v = uv3 ; uv3 = BlenderVector(u, 1-v)
				# assign
				f.uv = (uv1, uv2, uv3)

		return mesh

	def add_bones_to_armature(transform_nodes, parent_bone=None):

		for node in transform_nodes:
			if id(node) in node_ids:

				_bone = Blender.Armature.Editbone()
				_bone.head = BlenderVector(node.abs_transform.loc.to_tuple())

				# compute tail pos as arithmetic mean
				v = [_n.abs_transform.loc for _n in node.child_nodes if (id(_n) in node_ids and _n.bone_index in bone_set)]
				v = sum(v, Vector())*(1./len(v)) if (v and node.bone_index in bone_set) else node.abs_transform.loc

				# the bone's length must not be 0, otherwise Blender ignores it
				if (node.abs_transform.loc-v).len() < 0.025:
					v = node.abs_transform.loc + node.abs_transform.rot.get_matrix().col(2)*0.05
				_bone.tail = BlenderVector(v.to_tuple())

				if parent_bone: _bone.parent = parent_bone

				name = make_unique_bone_name(node.name, node.bone_index, armature.bones.keys())

				# add bone and its children
				armature.bones[name] = _bone
				add_bones_to_armature(node.child_nodes, _bone)
		##
		## armature, node_ids and bone_set are defined at the bottom

	def make_unique_bone_name(name, idx, collection):
		idx = '#%i'%idx if idx!=None else ''
		s = name[:30-len(idx)] + idx # max - 31 characters (?)
		i = 1
		while s in collection:
			s = '.%i'%i + idx
			s = name[:30-len(s)] + s
			i+= 1
		return s

	#---------------------------------------

	# get active scene
	scene = bpy.data.scenes.active

	#
	# add mesh objects (main geometry)
	#

	mesh_objects = []

	for group in geometry.index_groups:

		log( 'Index group "%s"' % group.name )

		data_group = geometry.data_groups[group.data_group_index]

		# define index mapping
		S = {} # { old_index -> new_index }
		for i, x in enumerate(sorted(set(chain(*group.indices)))): S[x] = i

		# map indices
		I = [(S[i], S[j], S[k]) for i, j, k in group.indices]

		# filtering function
		def select_data(data):
			return [x for i, x in enumerate(data) if i in S]

		V = select_data(data_group.vertices)

		# texture coords
		if data_group.tex_coords:
			T = select_data(data_group.tex_coords)
			T = [(T[i], T[j], T[k]) for i, j, k in I]
		else:
			T = group.tex_coords and group.tex_coords[:] # copy or None

		# also, Blender does not like triangles with zero-index vertex on 3rd position
		# as well as degenerate triangles (i.e., less than 3 different indices):
		#   https://www.blender.org/api/249PythonDoc/Mesh.MFaceSeq-class.html#extend
		#
		w = []
		for i, t in enumerate(I):
			if 0 == t[2]:
				I[i] = (t[2], t[0], t[1])
				log( '--Triangle # %i reordered:' % i, t, '->', I[i] )
				if T:
					uv1, uv2, uv3 = T[i]
					T[i] = (uv3, uv1, uv2)
			if len(set(t)) < 3:
				w.append(i)
				log( '--Triangle # %i' % i, t, 'removed' )
		for i in reversed(w):
			del I[i]
			if T:
				del T[i]
		w = None

		log( '--Creating mesh object (vertices: %i, triangles: %i)...' % (len(V), len(I)) )

		# create mesh and add it to the scene
		mesh = create_mesh(group.name, V, I, T)
		obj = scene.objects.new(mesh)
		obj.name = group.name # max - 21 characters

		# save original name and flags
		assert type(group.name) == str
		obj.addProperty('name', group.name) # Blender does not like Unicode here
		obj.addProperty('flags', '%08X' % group.flags)

		mesh_objects.append(obj) # save reference to current object

		log( '--Rigging:', data_group.bones and 'yes' or 'no' )

		# rigging
		#
		if data_group.bones:

			B = select_data(data_group.bones)
			W = select_data(data_group.weights)

			log( '--Assigning vertices to vertex groups...' )

			# map bones
			B = [tuple(group.bones[j] for j in b) for b in B]

			dd = dict() # { index -> unique_bone_name }
			for idx in group.bones:
				name = transform_tree and transform_tree.get_node(idx).name or 'bone'
				dd[idx] = name = make_unique_bone_name(name, idx, dd.values())
				# add vertex group
				mesh.addVertGroup(name)
			v_group_names = [dd.get(j) for j in xrange(max(dd)+1)]

			# assign vertices
			for i, (b, w) in enumerate(zip(B, W)):
				for wi, j in enumerate(b):
					if wi == 3:
						f = 1.0 - sum(w)
					else:
						f = w[wi]
					mesh.assignVertsToGroup(v_group_names[j], [i], f, 1) # 1 - Blender.Mesh.AssignModes.REPLACE

			v_group_names = dd = None

		# shape keys
		#
		if data_group.keys:

			log( '--Adding shape keys...' )

			keys = select_data(data_group.keys)
			dV = map(select_data, data_group.dVerts)

			log( '\x20\x20--Length of dV: (%i, %i, %i, %i)' % tuple(map(len, dV)) )

			# basis
			obj.insertShapeKey()

			for idx, s in enumerate(geometry.morph_names):

				_keys_f = filter(lambda t: idx in t[1], enumerate(keys))
				if _keys_f:

					s = '::'.join(s)

					log( '\x20\x20--Key "%s"' % s )

					obj.insertShapeKey()
					mesh.key.blocks[-1].name = s # set name

					block_verts = mesh.key.blocks[-1].data

					# modify mesh with dV
					#
					for i, key in _keys_f:
						j = key.index(idx)
						v = dV[j]
						if v:
							block_verts[i]+= BlenderVector(*v[i])

					obj.activeShape = 1 # return to basis

	#<- groups

	#
	# add bounding geometry
	#

	if settings['import_bmesh']:

		if geometry.static_bmesh:

			log( 'Creating static bounding mesh...' )

			V, I = geometry.static_bmesh

			mesh = Blender.Mesh.New('b_mesh')
			mesh.verts.extend(V)
			mesh.faces.extend(I)

			obj = scene.objects.new(mesh)
			obj.name = 'b_mesh'

		if geometry.dynamic_bmesh:

			log( 'Creating dynamic bounding mesh...' )

			mesh = Blender.Mesh.New('b_mesh')
			obj = scene.objects.new(mesh)
			obj.name = 'b_mesh'

			v_group_names = set()

			for idx, part in enumerate(geometry.dynamic_bmesh):
				if part:
					V, I = part
					S = {} # { old_index -> new_index }
					j = len(mesh.verts)
					for i, x in enumerate(sorted(set(chain(*I)))): S[x] = i+j

					rot, loc = geometry.inverse_transforms[idx]
					t = Transform(loc, rot).get_inverse()

					V = [t.transformPoint(Vector(*x)).to_tuple() for i, x in enumerate(V) if i in S]
					I = [(S[i], S[j], S[k]) for i, j, k in I]

					mesh.verts.extend(V)
					mesh.faces.extend(I)

					name = transform_tree and transform_tree.get_node(idx).name or 'bone'
					name = make_unique_bone_name(name, idx, v_group_names)
					v_group_names.add(name)
					mesh.addVertGroup(name)
					mesh.assignVertsToGroup(name, S.values(), 1.0, 1)

			mesh.calcNormals()

			v_group_names = None

			mesh_objects.append(obj)

	#
	# load inverse transforms (if any)
	#

	if geometry.inverse_transforms:

		v = tuple(chain(*chain(*geometry.inverse_transforms)))

		try:
			w = tuple(scene.properties['gmdc_inverse_transforms'])
			log( 'Scene already has inverse transforms (%i) stored in scene.properties["gmdc_inverse_transforms"]' % (len(w)/7) )
			if v != w and display_menu('The file has a different set of inverse transforms. Replace?',
			  ['Yes, replace inverse transforms.', 'No, keep previously loaded inverse transforms.'], choice_required=True) == 0:
				raise Exception()
		except:
			log( 'Saving inverse transforms in scene.properties["gmdc_inverse_transforms"]' )
			scene.properties['gmdc_inverse_transforms'] = v

	#
	# add armature (if any)
	#

	if transform_tree:

		bone_set = set(chain(*(group.bones or [] for group in geometry.index_groups)))

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

		if node_ids:

			log( 'Creating armature...' )
			log( '--Number of transform nodes (%i)' % len(node_ids) )

			armature = Blender.Armature.New()
			armature.envelopes = False
			armature.vertexGroups = True
			armature.drawType = Blender.Armature.STICK

			arm_obj = scene.objects.new(armature) # create armature object
			arm_obj.drawMode |= Blender.Object.DrawModes.XRAY

			# add bones
			armature.makeEditable()
			add_bones_to_armature(transform_tree.root_nodes)
			armature.update()

			log( '--Adding armature modifier(s)...' )

			# assign armature modifier
			#
			for obj in mesh_objects:
				modifier = obj.modifiers.append(Blender.Modifier.Types.ARMATURE)
				modifier[Blender.Modifier.Settings.VGROUPS  ] = True    # use vertex groups
				modifier[Blender.Modifier.Settings.ENVELOPES] = False   # not envelopes
				modifier[Blender.Modifier.Settings.OBJECT   ] = arm_obj

	scene.update()

#<- end


def begin_import():

	settings = {
		'import_bmesh':   btn_import_bmesh.val,
		'remove_doubles': btn_remove_doubles.val,
		'all_bones':      btn_all_bones.val,
		}

	_save_log = bool(btn_save_log.val)

	gmdc_filename = str_gmdc_filename.val.strip()
	cres_filename = str_cres_filename.val.strip()

	if not gmdc_filename:
		display_menu('Error!', ['Select GMDC file.'])
		return

	# create log file (if needed)
	if _save_log:
		s = gmdc_filename + '.import_log.txt'
		log( 'Opening log file "%s" for writing... ' % s )
		try:
			f = open(s, 'w')
		except IOError as e:
			error(e)
			display_menu('Error!', ['Could not open log file for writing.'])
			return
		# Ok
		set_log_file(f)

	#
	# begin import
	#

	log( '==Geometry Data Container Importer======' )
	log( 'GMDC file:', gmdc_filename )
	log( 'CRES file:', cres_filename )
	log( 'Settings:' )
	log( '--Import bounding geometry:', settings['import_bmesh'] )
	log( '--Remove doubles:   ', settings['remove_doubles'] )
	log( '--Import all bones: ', settings['all_bones'] )
	log()

	# load geometry
	log( 'Opening GMDC file "%s"...' % gmdc_filename )
	try:
		res = load_resource(gmdc_filename, _save_log and 2 or 1)
	except:
		print_last_exception()
		res = False
	if not res or res.nodes[0].type != 'cGeometryDataContainer':
		res and error( 'Not a GMDC file!' )
		close_log_file()
		display_menu('Error!', ['Could not load geometry file. See log for details.'])
		return
	geometry = res.nodes[0].geometry

	log()

	transform_tree = None
	if cres_filename:
		# load skeleton
		log( 'Opening CRES file "%s"...' % cres_filename )
		try:
			res = load_resource(cres_filename, _save_log and 2 or 1)
			if res and res.nodes[0].type == 'cResourceNode':
				transform_tree = build_transform_tree(res.nodes)
			else:
				res and error( 'Not a CRES file!' )
		except:
			print_last_exception()
		if not transform_tree:
			close_log_file()
			display_menu('Error!', ['Could not load resource node file. See log for details.'])
			return

		log()
		if _save_log:
			log( '==SKELETON==============================' )
			log( transform_tree )
			log()

	try:
		if settings['remove_doubles']:
			log( 'Removing doubles...' )
			geometry.remove_doubles()
			log()

		log( 'Creating objects...' )
		create_objects(geometry, transform_tree, settings)

	except:
		print_last_exception()
		display_menu('Error!', ['An error has occured. See log for details.'])

	else:
		# Ok
		log( 'Finished!' )

		Blender.Redraw()

		# exit prompt
		if display_menu("Import complete!", ['Quit']) == 0: Draw.Exit()

	finally:
		close_log_file()


########################################
##  GUI
########################################

def display_menu(caption, items, choice_required=False):
	b = True
	while b:
		choice = Draw.PupMenu('%s%%t|'%caption + "|".join('%s%%x%i'%(s, i) for i, s in enumerate(items)), 0x100)
		b = choice_required and choice < 0
	return choice


def draw_gui():

	global str_gmdc_filename, str_cres_filename, btn_import_bmesh, btn_all_bones, btn_remove_doubles, btn_save_log

	pos_y = 230 ; MAX_PATH = 200

	# frame

	Blender.BGL.glColor3f(0.75, 0.75, 0.75)
	Blender.BGL.glRecti(10, 10, 430, pos_y)

	pos_y-= 30

	# plugin's header

	s = "GMDC Importer (TS2)"
	Blender.BGL.glColor3f(0.8, 0.8, 0.8)
	Blender.BGL.glRecti(10, pos_y, 430, pos_y+30)
	Draw.Label(s, 20, pos_y, 400, 30)

	pos_y-= 30

	# GMDC file selector

	Draw.Label("GMDC file", 20, pos_y, 200, 20)
	pos_y-= 20
	Draw.BeginAlign()
	str_gmdc_filename = Draw.String("", 0x10, 20, pos_y, 300, 20, str_gmdc_filename.val, MAX_PATH, "Path to GMDC file")
	Draw.PushButton("Select file", 0x11, 320, pos_y, 100, 20, "Open file browser")
	Draw.EndAlign()

	pos_y-= 30

	# resource node file selector

	Draw.Label("Resource node file (optional)", 20, pos_y, 200, 20)
	pos_y-= 20
	Draw.BeginAlign()
	str_cres_filename = Draw.String("", 0x20, 20, pos_y, 300, 20, str_cres_filename.val, MAX_PATH, "Path to resource node file (CRES; optional, but recommended)")
	Draw.PushButton("Select file", 0x21, 320, pos_y, 100, 20, "Open file browser")
	Draw.EndAlign()

	pos_y-= 35

	# options

	Draw.BeginAlign()
	btn_import_bmesh = Draw.Toggle("Bound. mesh", 0x31, 20, pos_y, 100, 20, btn_import_bmesh.val, "Import bounding geometry")
	btn_remove_doubles = Draw.Toggle("Rm. doubles", 0x32, 120, pos_y, 100, 20, btn_remove_doubles.val, "If some vertices differ only in texture coordinates, then they are merged together (removes seams)")
	btn_all_bones = Draw.Toggle("All bones", 0x33, 220, pos_y, 100, 20, btn_all_bones.val, "Import all bones/transforms; otherwise, used bones only")
	btn_save_log = Draw.Toggle("Save log", 0x34, 320, pos_y, 100, 20, btn_save_log.val, "Write script's log data into file *.import_log.txt")
	Draw.EndAlign()

	pos_y-= 45

	# buttons

	Draw.BeginAlign()
	Draw.PushButton("Import", 1, 120, pos_y, 100, 30, "Import geometry (Ctrl + Enter)")
	Draw.PushButton("Exit", 0, 220, pos_y, 100, 30, "Terminate the script (Esc)")
	Draw.EndAlign()

#---------------------------------------
# event handlers

l_ctrl_key_pressed = 0
r_ctrl_key_pressed = 0

def set_gmdc_filename(filename):
	global gmdc_filename
	str_gmdc_filename.val = filename

def set_cres_filename(filename):
	global cres_filename
	str_cres_filename.val = filename

def event_handler(evt, val):
	global l_ctrl_key_pressed, r_ctrl_key_pressed
	if evt == Draw.ESCKEY and val:
		Draw.Exit()
	elif evt == Draw. LEFTCTRLKEY: l_ctrl_key_pressed = val
	elif evt == Draw.RIGHTCTRLKEY: r_ctrl_key_pressed = val
	elif evt == Draw.RETKEY and val and (l_ctrl_key_pressed or r_ctrl_key_pressed):
		begin_import()
		l_ctrl_key_pressed = 0
		r_ctrl_key_pressed = 0

def button_events(evt):
	if evt == 0:
		Draw.Exit()
	elif evt == 1:
		begin_import()
	elif evt == 0x11:
		Blender.Window.FileSelector(set_gmdc_filename, 'Select')
	elif evt == 0x21:
		Blender.Window.FileSelector(set_cres_filename, 'Select')


#-------------------------------------------------------------------------------
# set default values for gui elements and run event loop

str_gmdc_filename = Draw.Create("")
str_cres_filename = Draw.Create("")
btn_import_bmesh = Draw.Create(0)
btn_remove_doubles = Draw.Create(1)
btn_all_bones = Draw.Create(0)
btn_save_log = Draw.Create(0)

Draw.Register(draw_gui, event_handler, button_events)
