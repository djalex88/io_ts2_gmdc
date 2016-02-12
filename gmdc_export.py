#!BPY

"""
Name: 'GMDC (.gmdc)'
Blender: 249
Group: 'Export'
Tooltip: 'Export to TS2 GMDC file' """

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

import os
from struct import pack
from gmdc_tools import *
from itertools import count, repeat

import bpy, Blender
from Blender import Draw
from Blender.Mathutils import Vector as BlenderVector

########################################
##  Exporter
########################################

def prepare_geometry(settings):

	scene = bpy.data.scenes.active

	# get all mesh objects
	objects = filter(lambda obj: obj.type=='Mesh', scene.objects)

	# check whether visual transforms applied
	v = [obj for obj in objects if tuple(obj.rot)!=(0, 0, 0) or tuple(obj.size)!=(1, 1, 1)]
	if v:
		error( 'Error! The following mesh ' + ('objects have' if len(v)>1 else 'object has') + ' non-applied visual transforms:' )
		for obj in v:
			error( '\x20\x20%s -> rot: %s, size: %s' % (str(obj), str(obj.rot), str(obj.size)) )
		error( 'Solution: apply visual transforms (Ctrl+A).' )
		return False

	if settings['export_bmesh']:
		# does bounding mesh exist?
		v = [i for i, obj in enumerate(objects) if obj.name == settings['bmesh_name']]
		if not v:
			error( 'Error! Could not find bounding mesh.' )
			return False
		# remove from objects
		del objects[ v[0] ]

	if not objects:
		error( 'Error! Object list is empty.' )
		return False

	#
	# inverse transforms
	#

	inverse_transforms = None

	if settings['export_rigging']:

		if scene.properties.has_key('gmdc_inverse_transforms'):
			v = tuple(scene.properties['gmdc_inverse_transforms'])
			assert len(v)%7 == 0
			v = [chunk(t, 4) for t in chunk(v, 7)]
			inverse_transforms = v
		else:
			error( 'Error! No inverse transforms. (scene.properties["gmdc_inverse_transforms"] is not defined.)' )
			return False

	#
	# process main geometry
	#

	DATA_GROUPS = [] ; INDEX_GROUPS = []

	MORPH_NAMES = [] # [index] -> name

	log( 'Main geometry' )

	for obj in objects:

		log( str(obj) )

		# make current object active and activate basic shape key
		scene.objects.active = obj
		obj.activeShape = 1
		Blender.Window.EditMode(1)
		Blender.Window.EditMode(0)

		mesh = obj.getData(mesh=True)

		all_vertices = [] # for non-indexed vertices

		bone_indices = {} # used to enumerate bones { global_bone_index -> local_bone_index }

		# faces
		#
		mesh_faces = mesh.faces
		if not mesh_faces:
			error( 'Error! Mesh object has no faces.' )
			return False

		# all faces must have texture coordinates
		try:
			assert all(face.uv for face in mesh_faces)
		except:
			error( 'Error! Mesh object has faces with no texture coordinates.' )
			return False

		# tangents
		if settings['export_tangents']:
			mesh_tangents = [[tuple(x.xyz) for x in tangents] for tangents in mesh.getTangents()]
		else:
			mesh_tangents = repeat((None, None, None, None)) # no tangents

		obj_loc = obj.matrix[3].xyz

		# rigging
		rigging = settings['export_rigging']

		for face, tangents in zip(mesh_faces, mesh_tangents):
			verts = [tuple( (v.co + obj_loc).xyz ) for v in face.verts]
			norms = [tuple(v.no.xyz) for v in face.verts] if face.smooth else [tuple(face.no.xyz)] * len(verts)
			uv = [(t.x, 1.0-t.y) for t in face.uv] # OpenGL -> Direct3D
			if rigging:
				bones = []
				weights = []
				for v in face.verts:
					v_groups = mesh.getVertexInfluences(v.index)
					b = tuple()
					w = tuple()
					for name, f in v_groups:
						# get bone index
						s = name.split('#')
						try:
							assert f > 0.0
							idx = int(s[-1])
							if len(s) < 2 or idx < 0: raise Exception()
						except AssertionError:
							pass
						except:
							log( 'Warning! Could not extract bone index from vertex group name "%s". Influence on vertex # %i ignored.' % (name, v.index) )
						else:
							k = bone_indices.get(idx)
							if k == None:
								k = len(bone_indices)
								bone_indices[idx] = k
							b+= (k,)
							w+= (f,)
					if len(b) > 4:
						error( 'Error! Vertex # %i of mesh object "%s" is in more that 4 vertex groups.' % (v.index, obj.name) )
						return False
					# normalize weights
					f = sum(w)
					if f > 0.0001:
						w = tuple(x/f for x in w)
					else:
						w = tuple(0.0 for x in w) # ?
					bones  .append(b)
					weights.append(w)
			else:
				bones   = [(), (), (), ()]
				weights = [(), (), (), ()]

			# triangulate (if needed)
			if len(face.verts) == 4:
				order = (0, 1, 2, 0, 2, 3)
				verts    = [   verts[i] for i in order]
				norms    = [   norms[i] for i in order]
				uv       = [      uv[i] for i in order]
				bones    = [   bones[i] for i in order]
				weights  = [ weights[i] for i in order]
				tangents = [tangents[i] for i in order]

			# add vertices to list
			all_vertices+= zip(verts, norms, uv, bones, weights, tangents)

		#<- faces

		mesh_tangents = None

		#
		# morphs / vertex animations
		#

		morphing = settings['export_morphs'] and mesh.key and len(mesh.key.blocks) > 1
		if morphing:

			morphing = settings['export_morphs'] # 1 - dVerts only; 2 - dVerts & dNorms

			log( '--Processing shape keys...' )

			mesh_morphs = [] # current mesh morphs
			first_new_morph_index = None # first new morph that is not present in MORPH_NAMES

			dVerts = []
			dNorms = []

			# compute differences

			for k, key_block in enumerate(mesh.key.blocks[1:], 2):

				name = tuple(key_block.name.strip().split('::'))
				if len(name) != 2:
					error( 'Error! Invalid morph name: "%s"' % '::'.join(name) )
					return False

				try:
					j = MORPH_NAMES.index(name)
				except ValueError:
					# new morph
					j = len(MORPH_NAMES)
					MORPH_NAMES.append(name)
					if first_new_morph_index == None: first_new_morph_index = j
				mesh_morphs.append(j)

				log( '--Key "%s" (%i)' % (name, k) )

				# activate morph
				obj.activeShape = k
				Blender.Window.EditMode(1)
				Blender.Window.EditMode(0)
				key_block_verts = key_block.getData()

				# add difference arrays
				dv = [] ; dVerts.append(dv)
				dn = [] ; dNorms.append(dn)

				# loop through all faces and compute vertex differences
				j = 0
				for face in mesh_faces:
					verts = [(key_block_verts[v.index] + obj_loc) for v in face.verts]
					norms = [v.no for v in face.verts] if face.smooth else [face.no] * len(verts)
					if len(face.verts) == 4:
						order = (0, 1, 2, 0, 2, 3)
						verts = [verts[i] for i in order]
						norms = [norms[i] for i in order]

					for v, w in zip(verts, norms):
						dv.append(tuple((v - BlenderVector(all_vertices[j][0])).xyz))
						dn.append(tuple((w - BlenderVector(all_vertices[j][1])).xyz))
						j+= 1
				assert j == len(all_vertices)

			log( '--Packing...' )

			k = len(all_vertices)

			keys = [[] for i in xrange(k)]

			if morphing == 2: # vertices and normals
				v = [[] for i in xrange(k)]
				w = [[] for i in xrange(k)]
				for i, dv, dn in zip(mesh_morphs, dVerts, dNorms): # loop through all difference arrays (morphs)
					for x, y, k, a, b in zip(dv, dn, keys, v, w):
						if x != (0.0, 0.0, 0.0) or y != (0.0, 0.0, 0.0): # vertex affected
							if len(k) == 4:
								error( 'Error! Some vertices are affected by more than 4 morphs (shape keys).' )
								return False
							# morph index
							k.append(i)
							# difference
							a.append(x)
							b.append(y)
				dVerts = v ; v = None
				dNorms = w ; w = None

			else: # vertices only
				v = [[] for i in xrange(k)]
				for i, dv in zip(mesh_morphs, dVerts):
					for x, k, a in zip(dv, keys, v):
						if x != (0.0, 0.0, 0.0):
							if len(k) == 4:
								error( 'Error! Some vertices are affected by more than 4 morphs (shape keys).' )
								return False
							# morph index
							k.append(i)
							# difference
							a.append(x)
				dVerts = v ; v = None

			assert len(dVerts) == len(all_vertices)

			if not any(keys):
				log( '--Differeces between shape keys of mesh object "%s" were not detected.' % obj.name )
				morphing = False
				if first_new_morph_index != None:
					del MORPH_NAMES[first_new_morph_index : ] # remove newly added morph names

			else:
				keys = map(tuple, keys)

				j = max(len(v) for v in dVerts) # number of difference arrays
				log( '--Number of arrays:', j )

				dVerts = [(tuple(dv) + ((0.0, 0.0, 0.0),)*4)[:j] for dv in dVerts] # align

				if morphing == 2:
					dNorms = [(tuple(dn) + ((0.0, 0.0, 0.0),)*4)[:j] for dn in dNorms]
					for i, k, dv, dn in zip(count(), keys, dVerts, dNorms):
						all_vertices[i]+= (k, dv, dn)
				else:
					for i, k, dv     in zip(count(), keys, dVerts):
						all_vertices[i]+= (k, dv)

			dVerts = dNorms = None ; keys = None

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

		unique_verts = [v for v, i in sorted(unique_verts.iteritems(), key=lambda x: x[1])]

		log( '\x20\x20--Vertex count: %i -> %i' % (len(all_vertices), len(unique_verts)) )

		del all_vertices

		V, N, T, B, W, X, K, dV, dN = map(list, zip(*unique_verts)) + ([None,None,None] if not morphing else [None]*(2-morphing))

		del unique_verts

		#
		# add new data group or extend an existing one
		#

		# does the mesh have rigging data ?
		rigging = rigging and any(B)

		# try to find a suitable data group
		group = None
		for i, g in enumerate(DATA_GROUPS):
			b1 = bool(g.bones) == rigging
			if morphing:
				b2 = sum(bool(x) for x in g.dVerts) == len(dV[0]) # same number of difference arrays
			else:
				b2 = not bool(g.dVerts[0]) # no difference arrays
			if b1 and b2:
				# found
				ref_group, group = i, g
				break
		if group:
			k = group.count
			indices = map(lambda x: x+k, indices) # shift indices
			log( '--Extending group # %i...' % ref_group )
		else:
			ref_group = len(DATA_GROUPS)
			group = DataGroup() ; DATA_GROUPS.append(group)
			log( '--Adding new group # %i...' % ref_group )

		# add vertices to group
		#
		group.vertices.extend(V)
		group.normals.extend(N)
		group.tex_coords.extend(T)
		if rigging:
			group.bones.extend(B)
			group.weights.extend(W)
		if settings['export_tangents']:
			group.tangents.extend(X)
		if morphing:
			group.keys.extend(K)
			dV = map(list, zip(*dV)) + [[], [], []]
			for v, w in zip(group.dVerts, dV): v.extend(w)
			if morphing > 1:
				dN = map(list, zip(*dN)) + [[], [], []]
				for v, w in zip(group.dNorms, dV): v.extend(w)

		del V, N, T, B, W, X, K, dV, dN

		k = group.count
		group.count = len(group.vertices)
		log( '\x20\x20--Vertex count:', '%i -> %i' % (k, group.count) if k else group.count )

		#
		# create index group
		#

		# name
		name = obj.name
		if settings['use_obj_props']:
			try:
				x = obj.getProperty('name')
				assert x.type == 'STRING' and x.data != ''
			except AssertionError:
				log( 'Warning! Invalid data for property "name". Ignored.' )
			except:
				pass
			else:
				name = x.data

		log( '--Creating new index group # %i, "%s" (triangles: %i)...' % (len(INDEX_GROUPS), name, len(indices)/3) )

		group = IndexGroup(name) ; INDEX_GROUPS.append(group)
		group.data_group_index = ref_group
		group.indices = chunk(tuple(indices), 3) # triangles

		indices = None

		# flags
		if settings['use_obj_props']:
			x = None
			try:
				x = obj.getProperty('flags')
				try:
					assert x.type == 'STRING'
					x = int(x.data, 16)
					log( '--Flags:', to_hex(pack('<L', x)) )
				except:
					x = None
					log( 'Warning! Invalid data for property "flags". Ignored.' )
				else:
					group.flags = x
			except:
				# property not found
				pass

		# bone index mapping
		if rigging:
			# order items by local bone index
			bone_indices = sorted(bone_indices.iteritems(), None, key=lambda x: x[1])
			# put global indices
			group.bones = []
			for idx, j in bone_indices:
				if idx >= len(inverse_transforms):
					error( 'Error! No inverse transform for bone # %i.' % idx )
					return False
				group.bones.append(idx)

		bone_indices = None

	#<- objects

	#
	# bounding geometry
	#

	static_bmesh = None ; dynamic_bmesh = None

	if settings['export_bmesh']:

		bmesh_obj = Blender.Object.Get(settings['bmesh_name'])
		mesh = bmesh_obj.getData(mesh=True)

		obj_loc = bmesh_obj.matrix[3].xyz

		log( 'Bounding mesh object %s:' % bmesh_obj )

		if settings['export_rigging']:

			dynamic_bmesh = []

			v_groups = {} # { bone_index -> v_group_name }
			for name in mesh.getVertGroupNames():
				# get bone index
				s = name.split('#')
				try:
					idx = int(s[-1])
					if len(s) < 2 or idx < 0: raise Exception()
				except:
					error( 'Error! Could not extract bone index from vertex group name "%s".' % name )
					return False
				v_groups[idx] = name

			for idx in xrange(max(v_groups)+1):

				if idx in v_groups:

					indices = set(v[0] for v in mesh.getVertsFromGroup(v_groups[idx], 1) if v[1] > 0.0) # do not accept vertices with weight == 0

					I = [] ; dd = {}
					for face in mesh.faces:
						vi = [v.index for v in face.verts]
						flags = sum(2**i for i, j in enumerate(vi) if j in indices)
						if (flags & 0b0111) == 0b0111: # (0, 1, 2)
							I.extend([
								dd.setdefault(vi[0], len(dd)),
								dd.setdefault(vi[1], len(dd)),
								dd.setdefault(vi[2], len(dd))])
						if (flags & 0b1101) == 0b1101: # (0, 2, 3)
							I.extend([
								dd.setdefault(vi[0], len(dd)),
								dd.setdefault(vi[2], len(dd)),
								dd.setdefault(vi[3], len(dd))])
					if dd:
						V = []

						# get inverse transform
						#
						if idx >= len(inverse_transforms):
							error( 'Error! No inverse transform for bone # %i.' % idx )
							return False

						rot, loc = inverse_transforms[idx]
						t = Transform(loc, rot)

						dd = sorted(dd.iteritems(), None, key=lambda x: x[1])

						# set coords
						for i, j in dd:
							# transform coord into bone space
							a = mesh.verts[i].co.xyz + obj_loc
							a = t.transformPoint( Vector(a.x, a.y, a.z) ).to_tuple()
							V.append(a)

						I = chunk(I, 3)

						dynamic_bmesh.append((V, I))
						log( '--Part # %02i -> vertices: %i, triangles: %i' % (idx, len(V), len(I)) )

					else:
						dynamic_bmesh.append(None)
				else:
					dynamic_bmesh.append(None)

			if not any(dynamic_bmesh):
				dynamic_bmesh = None

		else:
			V = [tuple( (v.co + obj_loc).xyz ) for v in mesh.verts]
			I = []
			for face in mesh.faces:
				if len(face.verts) == 3:
					I.append( tuple(v.index for v in face.verts) )
				else:
					I.append( (face.verts[0].index, face.verts[1].index, face.verts[2].index) )
					I.append( (face.verts[0].index, face.verts[2].index, face.verts[3].index) )
			static_bmesh = (V, I)

			log( '--Static bounding mesh -> vertices: %i, triangles: %i' % (len(V), len(I)) )

	return GeometryData(DATA_GROUPS, INDEX_GROUPS, inverse_transforms, MORPH_NAMES, static_bmesh, dynamic_bmesh)


#-------------------------------------------------------------------------------
# this function does basic checks and initiates the exporter

def begin_export():

	Blender.Window.EditMode(0)

	settings = {
		'SGResource':       str_resource_name.val.strip(),
		'name_suffix':      btn_name_suffix.val,
		'export_rigging':   btn_export_rigging.val,
		'export_tangents':  btn_export_tangents.val,
		'export_bmesh':     btn_export_bmesh.val,
		'bmesh_name':       str_bmesh_name.val.strip(),
		'export_morphs':    menu_export_morphs.val,
		'use_obj_props':    btn_use_obj_props.val,
		}

	_save_log = bool(btn_save_log.val)

	gmdc_filename = str_gmdc_filename.val.strip()

	if not gmdc_filename:
		display_menu('Error!', ['Select filename for GMDC file.']) ; return
	elif not os.path.basename(gmdc_filename):
		display_menu('Error!', ['Invalid filename for GMDC file.']) ; return
	elif os.path.isfile(gmdc_filename):
		if display_menu("File '%s' exists. Rewrite?" % os.path.basename(gmdc_filename), ['Yes, rewrite.']) != 0: return

	if settings['export_bmesh'] and not settings['bmesh_name']:
		display_menu('Error!', ['Enter bounding mesh\'s object name.'])
		return

	# create log file (if needed)
	if _save_log:
		s = gmdc_filename + '.export_log.txt'
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
	# begin export
	#

	log( '==Geometry Data Container Exporter======' )
	log( 'GMDC File:', gmdc_filename )
	log( 'Settings:' )
	log( '--SGResource:',        settings['SGResource'] and '"%s"' % settings['SGResource'] or 'none' )
	log( '--Name suffix:      ', settings['name_suffix'] )
	log( '--Export rigging:   ', settings['export_rigging'] )
	log( '--Export tangents:  ', settings['export_tangents'] )
	log( '--Export bounding geometry:', settings['export_bmesh'] )
	log( '--Bounding mesh name:',settings['bmesh_name'] and '"%s"' % settings['bmesh_name'] or 'none' )
	log( '--Export morphs:    ', settings['export_morphs'] )
	log( '--Use properties:   ', settings['use_obj_props'] )
	log()

	s = settings['SGResource']
	if not s:
		s = os.path.basename(gmdc_filename).split(".")
		s = ".".join(s[:-1] or s)
	if settings['name_suffix']:
		s+= '_tslocator_gmdc'

	log( 'Preparing geometry...' )
	geometry = None
	try:
		geometry = prepare_geometry(settings)
	except:
		print_last_exception()
	if not geometry:
		display_menu('Error!', ['An error has occured while preparing geometry. See log for details.'])
		close_log_file()
		return

	log()
	log( 'Creating GMDC file "%s"... ' % gmdc_filename )
	try:
		create_gmdc_file(gmdc_filename, s, geometry)
	except:
		print_last_exception()
		display_menu('Error!', ['An error has occured while creating GMDC file. See log for details.'])
	else:
		# Ok
		log( 'Finished!' )

		# exit prompt
		if display_menu("Export complete!", ['Quit']) == 0: Draw.Exit()

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

	global str_gmdc_filename, str_cres_filename, str_resource_name, btn_name_suffix, \
		btn_export_tangents, btn_export_rigging, btn_export_bmesh, btn_save_log, \
		menu_export_morphs, btn_use_obj_props, str_bmesh_name

	pos_y = 340 ; MAX_PATH = 200

	# frame

	Blender.BGL.glColor3f(0.75, 0.75, 0.75)
	Blender.BGL.glRecti(10, 10, 430, pos_y)

	pos_y-= 30

	# plugin's header

	s = "GMDC Exporter (TS2)"
	Blender.BGL.glColor3f(0.8, 0.8, 0.8)
	Blender.BGL.glRecti(10, pos_y, 430, pos_y+30)
	Draw.Label(s, 20, pos_y, 400, 30)

	pos_y-= 30

	# GMDC file selector

	Draw.Label("GMDC file (output)", 20, pos_y, 200, 20)
	pos_y-= 20
	Draw.BeginAlign()
	str_gmdc_filename = Draw.String("", 0x10, 20, pos_y, 300, 20, str_gmdc_filename.val, MAX_PATH, "Path to GMDC file")
	Draw.PushButton("Select file", 0x11, 320, pos_y, 100, 20, "Open file browser")
	Draw.EndAlign()

	pos_y-= 35

	# geometry name

	Blender.BGL.glColor3f(0.7, 0.7, 0.7)
	Blender.BGL.glRecti(20, pos_y-60, 420, pos_y+20)

	Draw.Label("SGResource name (optional)", 25, pos_y, 400, 20) ; pos_y-= 20
	Draw.Label("If not provided then GMDC filename is used", 25, pos_y, 400, 20) ; pos_y-= 30
	Draw.BeginAlign()
	str_resource_name = Draw.String("", 0x50, 70, pos_y, 180, 20, str_resource_name.val, 50, "SGResource name of this geometry")
	btn_name_suffix = Draw.Toggle("_tslocator_gmdc", 0x51, 250, pos_y, 120, 20, btn_name_suffix.val, "Add default suffix")
	Draw.EndAlign()

	pos_y-= 45

	# options

	Draw.BeginAlign()
	btn_export_rigging = Draw.Toggle("Rigging", 0x31, 20, pos_y, 100, 20, btn_export_rigging.val, "Export rigging data (bone indices, weights)")
	btn_export_tangents = Draw.Toggle("Tangents", 0x32, 120, pos_y, 100, 20, btn_export_tangents.val, "Export tangents (required for bump mapping)")
	btn_export_bmesh = Draw.Toggle("Bound. mesh", 0x33, 220, pos_y, 100, 20, btn_export_bmesh.val, "Export bounding geometry")
	btn_save_log = Draw.Toggle("Save log", 0x34, 320, pos_y, 100, 20, btn_save_log.val, "Write script's log data into file *.export_log.txt")
	Draw.EndAlign()

	pos_y-= 30

	Draw.BeginAlign()
	menu_export_morphs = Draw.Menu("Export morphs %t|Do not export morphs %x0|Diff. in v.coords only %x1|Diff. in v.coords and normals %x2", 0x35, 20, pos_y, 200, 20, menu_export_morphs.val)
	btn_use_obj_props = Draw.Toggle("Use object properties", 0x36, 220, pos_y, 200, 20, btn_use_obj_props.val, "Properties can be assigned in logic panel")
	Draw.EndAlign()

	pos_y-= 30

	# bounding mesh name

	Draw.Label("Bounding mesh:", 20, pos_y, 100, 20)
	str_bmesh_name = Draw.String("", 0x40, 120, pos_y, 200, 20, str_bmesh_name.val, 50, "Name of mesh object that will be exported as bounding mesh")

	pos_y-= 50

	# buttons

	Draw.BeginAlign()
	Draw.PushButton("Export", 1, 120, pos_y, 100, 30, "Export geometry (Ctrl + Enter)")
	Draw.PushButton("Exit", 0, 220, pos_y, 100, 30, "Terminate the script (Esc)")
	Draw.EndAlign()


#---------------------------------------
# event handlers

l_ctrl_key_pressed = 0
r_ctrl_key_pressed = 0

def set_gmdc_filename(filename):
	global gmdc_filename
	str_gmdc_filename.val = filename

def event_handler(evt, val):
	global l_ctrl_key_pressed, r_ctrl_key_pressed
	if evt == Draw.ESCKEY and val:
		Draw.Exit()
	elif evt == Draw. LEFTCTRLKEY: l_ctrl_key_pressed = val
	elif evt == Draw.RIGHTCTRLKEY: r_ctrl_key_pressed = val
	elif evt == Draw.RETKEY and val and (l_ctrl_key_pressed or r_ctrl_key_pressed):
		begin_export()
		l_ctrl_key_pressed = 0
		r_ctrl_key_pressed = 0

def button_events(evt):
	if evt == 0:
		Draw.Exit()
	elif evt == 1:
		begin_export()
	elif evt == 0x11:
		Blender.Window.FileSelector(set_gmdc_filename, 'Select', Blender.sys.makename(ext='.gmdc'))


#-------------------------------------------------------------------------------
# set default values for GUI elements and run event loop

str_gmdc_filename   = Draw.Create("")
str_resource_name   = Draw.Create("")
btn_name_suffix     = Draw.Create(1)
btn_export_rigging  = Draw.Create(0)
btn_export_tangents = Draw.Create(0)
btn_export_bmesh    = Draw.Create(0)
btn_save_log        = Draw.Create(0)
btn_use_obj_props   = Draw.Create(0)
menu_export_morphs  = Draw.Create(0)
str_bmesh_name      = Draw.Create("b_mesh")

Draw.Register(draw_gui, event_handler, button_events)
