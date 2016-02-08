#!BPY

"""
Name: 'TS2 Object Footprint'
Blender: 249
Group: 'Export'
Tooltip: 'Generate footprint for TS2 object' """

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
from math import floor, ceil
from itertools import product
from gmdc_tools import log, error, set_log_file, close_log_file, print_last_exception, load_resource
from gmdc_tools._resfile import DataListExtension, str_footprint

import bpy, Blender
from Blender import Draw
from Blender.Mathutils import Vector, Intersect

#---------------------------------------

scene = bpy.data.scenes.active

def generate_footprint():

	# get mesh objects
	objects = filter(lambda obj: obj.type=='Mesh' and obj.name.lower().startswith('footprint'), scene.objects)

	if not objects:
		error( 'Error! Object list is empty. (No mesh objects whose names begin with "footprint".)' )
		return False

	# check whether visual transforms applied
	v = [obj for obj in objects if tuple(obj.rot)!=(0, 0, 0) or tuple(obj.size)!=(1, 1, 1)]
	if v:
		error( 'Error! The following mesh ' + ('objects have' if len(v)>1 else 'object has') + ' non-applied visual transforms:' )
		for obj in v:
			error( '\x20\x20%s -> rot: %s, size: %s' % (str(obj), str(obj.rot), str(obj.size)) )
		error( 'Solution: apply visual transforms.' )
		return False

	footprint = []

	for obj in objects:

		log( str(obj) )

		mesh = obj.getData(mesh=True)

		obj_loc = obj.matrix[3].xyz + Vector(0.5, 0.5, 0)

		name = obj.name.split('.')
		name = name[1] if len(name)>1 else "0"

		def test_point(x0, y0, i, j):

			x = x0 + 0.0625*(i+0.5)
			y = y0 + 0.0625*(j+0.5)

			ray, orig = Vector(0, 0, 1), Vector(x, y, 0)

			for face in mesh.faces:
				verts = [v.co+obj_loc for v in face.verts]

				if Intersect(verts[0], verts[1], verts[2], ray, orig, 1) or \
				 ( len(face.verts) == 4 and \
				   Intersect(verts[0], verts[2], verts[3], ray, orig, 1) ): return True

			return False

		# bounding box
		box = obj.getBoundBox(1)
		X, Y, Z = zip(*map(tuple, box))
		Z = None # not used

		minx, maxx = int(floor(min(X)+0.5)), int(ceil(max(X)+0.5))
		miny, maxy = int(floor(min(Y)+0.5)), int(ceil(max(Y)+0.5))

		data = [(0x02, 'minx', minx), (0x02, 'maxx', maxx-1), (0x02, 'miny', miny), (0x02, 'maxy', maxy-1)]

		log( '--Name: "%s"' % name )
		log( '--Size: %i x %i' % (maxx-minx, maxy-miny) )

		for x, y in product(xrange(minx, maxx), xrange(miny, maxy)):

			key = '(%i,%i)' % (x, y)

			s = ''

			for j in xrange(16):
				a = sum(2**i for i in xrange(16) if test_point(x, y, i, j))
				s+= pack('<H', a)
			data.append( (0x09, key, s) )

		footprint.append( (0x07, name, data) )

	#<- objects

	return (0x07, 'footprint', footprint)


#---------------------------------------

def display_menu(caption, items, choice_required=False):
	b = True
	while b:
		choice = Draw.PupMenu('%s%%t|'%caption + "|".join('%s%%x%i'%(s, i) for i, s in enumerate(items)), 0x100)
		b = choice_required and choice < 0
	return choice


def update_cres(cres_filename):

	Blender.Window.EditMode(0)

	_save_log = display_menu('Save log?', ['Yes', 'No'], True) == 0

	# create log file (if needed)
	if _save_log:
		s = cres_filename + '.gen_footprint_log.txt'
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

	log( '==TS2 Object Footprint Generator========' )
	log( 'CRES File:', cres_filename )
	log()

	# load CRES file
	log( 'Opening CRES file "%s"...' % cres_filename )
	try:
		res = load_resource(cres_filename, _save_log and 2 or 1)
	except:
		print_last_exception()
		res = False
	if not res or res.nodes[0].type != 'cResourceNode':
		res and error( 'Not a GMDC file!' )
		close_log_file()
		display_menu('Error!', ['Could not load resource node file. See log for details.'])
		return

	log()

	# get footprint extension node
	#
	v = [node for node in res.nodes if node.type=='cDataListExtension' and node.Ext_data[1]=='footprint']
	if v:
		node = v[0]
		log( 'Footprint extension node found (%i).' % node.index )
	else:
		log( 'Adding footprint extension node...' )
		node = DataListExtension(len(res.nodes))
		res.nodes.append(node)
		res.nodes[0].extensions.append((1, 0, node.index))

	log()

	# export
	#
	log( 'Processing objects...' )
	footprint = None
	try:
		footprint = generate_footprint()
		assert bool(footprint)
		node.Ext_data = footprint ; footprint = None

		log()
		log( 'Saving file...' )
		res.save()

	except:
		footprint==None and print_last_exception()
		display_menu('Error!', ['An error has occured. See log for details.'])

	else:
		# Ok
		log()
		log( 'New footprint:\n' + str_footprint(node.Ext_data[2]) )

		log( 'Finished!' )

	finally:
		close_log_file()


#---------------------------------------
# run

if not filter(lambda obj: obj.type=='Mesh' and obj.name.lower().startswith('footprint'), scene.objects):

	display_menu('Error!', ['No mesh objects whose names begin with "footprint".'])

else:
	Blender.Window.FileSelector(update_cres, 'Update CRES')

