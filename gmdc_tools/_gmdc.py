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


__all__ = ['DataGroup', 'IndexGroup', 'GeometryData', 'create_gmdc_file']

from struct import pack, unpack

from ._common import *
from ._node import _SGNode

# Geometry data
#
class DataGroup(object):
	def __init__(self):
		self.count      = 0
		self.vertices   = list()
		self.normals    = list()
		self.tex_coords = list()
		self.bones      = list()
		self.weights    = list()
		self.tangents   = list()
		self.mask       = list()
		self.keys       = list()
		self.dVerts = [[], [], [], []]
		self.dNorms = [[], [], [], []]
		self.tex_coords2 = []

class IndexGroup(object):
	def __init__(self, name):
		self.name = name
		self.data_group_index = None
		self.indices = None
		self.tex_coords = None
		self.tex_coords2 = None
		self.bones = None
		self.flags = 0xffffffff

class GeometryData(object):
	def __init__(self, data_groups, index_groups, inverse_transforms=None, morph_names=None, static_bmesh=None, dynamic_bmesh=None):
		self.data_groups = data_groups
		self.index_groups = index_groups
		self.inverse_transforms = inverse_transforms
		self.morph_names = morph_names
		self.static_bmesh = static_bmesh
		self.dynamic_bmesh = dynamic_bmesh

	def remove_doubles(self):
		_rm_doubles(self)


class GeometryDataContainer(_SGNode):

	def __init__(self, index):
		self.index = index
		self.type = 'cGeometryDataContainer'
		self.version = 0x04

	def read(self, f, log_level=1):
		s = f.read(27)
		if s != b'\x16cGeometryDataContainer\x87\x86\x4F\xAC':
			error( 'Error! cGeometryDataContainer header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		if not self._read_check_version(f, 0x04) or not self._read_cSGResource(f):
			return False
		self.geometry = _load_geometry_data(f, log_level)
		return bool(self.geometry)

	def write(self, f):
		f.write(b'\x16cGeometryDataContainer\x87\x86\x4F\xAC')
		self._write_version(f)
		self._write_cSGResource(f)
		_write_geometry_data(f, self.geometry)

	def __str__(self):
		s = 'cGeometryDataContainer'
		g = self.geometry
		s+= '\n' + self._str_cSGResource() + '\n'
		s+= '--Data groups (%i):\n' % len(g.data_groups)
		for i, group in enumerate(g.data_groups):
			# vertex format
			data_list = [group.vertices, group.normals, group.tex_coords, group.tex_coords2, group.bones, group.weights, group.tangents, group.mask, group.keys]
			s+= '\x20\x20%i - Elements:%5i, ' % (i, group.count)
			s+= 'vertex: <'
			for data, ch in zip(data_list, 'VNT2BWXMK'):
				if data:
					s+= ch
			num_dV = sum(map(bool, group.dVerts))
			if num_dV:
				s+= ' dV(%i)' % num_dV
			num_dN = sum(map(bool, group.dNorms))
			if num_dN:
				s+= ' dN(%i)' % num_dN
			s+= '>\n'
		s+= '--Index groups (%i):\n' % len(g.index_groups)
		for i, group in enumerate(g.index_groups):
			s+= '\x20\x20%i - Name: "%s", triangles: %i, data group: %i\n' % (i, group.name, len(group.indices), group.data_group_index)
		s+= '--Inverse transforms: ' + (str(len(g.inverse_transforms)) if g.inverse_transforms else 'None') + '\n'
		s+= '--Morphs: ' + (str(len(g.morph_names)) if g.morph_names else 'None') + '\n'
		bmesh_types = [
			'static' if g.static_bmesh else '',
			'dynamic (%i)'%len(g.dynamic_bmesh) if g.dynamic_bmesh else '',
		]
		s+= '--Bounding geometry: ' + (str(filter(bool, bmesh_types)) or 'None')
		return s

	def __repr__(self):
		return self.__str__()


########################################
##  Geometry loader
########################################

def _load_geometry_data(f, log_level):

	#
	# sections
	#

	dd = {
		b'\x81\x07\x83\x5B': ('Vertices',    'V'),
		b'\x8B\x07\x83\x3B': ('Normals',     'N'),
		b'\xAB\x07\x83\xBB': ('TexCoords',   'T'),
		b'\x11\x01\xD7\xFB': ('BoneIndices', 'B'),
		b'\x05\x01\xD7\x3B': ('BoneWeights', 'W'),
		b'\xA0\x2B\xD9\x89': ('Tangents',    'X'),
		b'\xE1\xCF\xF2\x5C': ('DiffVerts',  'dV'),
		b'\x6A\x3A\x6F\xCB': ('DiffNorms',  'dN'),
		b'\xDC\xCF\xF2\xDC': ('DiffKeys',    'K'),
		b'\x95\x07\x83\xDB': ('DeformMask',  'M'),
		b'\x82\xEE\x4D\x7C': ('0x7C4DEE82',  '1'),
		b'\x5C\xFC\x4A\x5C': ('0x5C4AFC5C',  '2'),
		b'\x56\xFC\x4A\x1C': ('0x1C4AFC56',  '3'),
		}

	if log_level:
		log( '//// Reading GMDC...' )
		log( '==SECTIONS==============================' )

	SECTIONS = []

	# number of sections
	#
	section_count = unpack('<l', f.read(4))[0]
	log_level and log( 'Number of sections: %i' % section_count )

	for k in xrange(section_count):

		offset = f.tell()
		i = unpack('<l', f.read(4))[0]
		s1, s2 = dd[f.read(4)]
		sub_idx, type_of_data, unknown1, j = unpack('<4l', f.read(16))

		log_level and log( 'Section [%03i] @ %08x - ' % (k, offset) + s1 + (j==0 and (i and '\x20(empty, but count is %i)'%i or '\x20(empty)') or '') )
		if i and log_level > 1:
			log( '--Element count:',   i )
			log( '--Sub index:', sub_idx )
			log( '--Type of data:', type_of_data )
			log( '--Unknown:',  unknown1 )
			log( '--Size (in bytes):', j )

		if i == 0:
			#
			# empty section
			#
			assert j == 0

			SECTIONS.append( (None, None, None) )

		elif s1 in (
			'Vertices',
			'Normals',
			'TexCoords',
			'BoneWeights',
			'Tangents',
			'DiffVerts',
			'DiffNorms'
			):
			# component count
			cc = type_of_data + 1

			assert i*cc*4 == j

			data = chunk(unpack('<%if'%(i*cc), f.read(j)), cc)
			SECTIONS.append( (s2, sub_idx, data) )

		elif s1 == 'BoneIndices':

			assert i*4 == j

			data = unpack('%iB'%j, f.read(j))

			log_level>1 and log( '--Index range: [%i-%i]' % (min(data), max(x for x in data if x!=0xff)) )

			data = [v[:(v+(0xff,)).index(0xff)] for v in chunk(data, 4)]
			SECTIONS.append( ('B', sub_idx, data) )

		elif s1 == 'DiffKeys' or s1 == 'DeformMask':

			assert i*4 == j

			data = chunk(unpack('%iB'%j, f.read(j)), 4)
			SECTIONS.append( (s2, sub_idx, data) )

		else: # 0x7C4DEE82, 0x5C4AFC5C, 0x1C4AFC56

			# component count
			cc = type_of_data + 1

			V = chunk(unpack('<%if'%(j//4), f.read(j)), cc)

			log_level>1 and log( '--Number of vectors, indices:', len(V) )


		# indices
		#
		if s1 in ('0x7C4DEE82', '0x5C4AFC5C', '0x1C4AFC56') and 'V' in locals() and V != None:

			i = unpack('<l', f.read(4))[0]
			s = f.read(i*2)
			I = unpack('<%iH'%i, s)

			assert len(I) == len(V)

			# ignore this data
			SECTIONS.append( (None, None, None) )

		else:
			assert f.read(4) == b'\x00\x00\x00\x00'

	#<-

	#
	# groups of data
	#

	log_level and log( '==GROUPS================================' )

	DATA_GROUPS = []

	# number of groups
	#
	group_count = unpack('<l', f.read(4))[0]

	log_level and log( 'Number of groups: %i' % group_count )

	for k in xrange(group_count):

		# add new group
		group = DataGroup() ; DATA_GROUPS.append(group)

		# number of sections for this group
		i = unpack('<l', f.read(4))[0]

		# section indices
		s = f.read(i*2)
		indices = unpack('<%iH'%i, s)

		log_level and log( 'Group %i:' % k, indices )

		# element count
		group.count = unpack('<l', f.read(4))[0]

		for idx in indices:
			type, sub_index, data = SECTIONS[idx]
			if type:
				if type in ('T', 'dV', 'dN'):
					if sub_index not in (0, 1, 2, 3):
						error( 'Error! Section sub_index is out of range. (Section type: %s)' % type )
						return False
				else:
					if sub_index != 0:
						error( 'Error! Section sub_index is not zero. (Section type: %s)' % type )
						return False
				if   type == 'V': v = group.vertices
				elif type == 'N': v = group.normals
				elif type == 'B': v = group.bones
				elif type == 'W': v = group.weights
				elif type == 'X': v = group.tangents
				elif type == 'M': v = group.mask
				elif type == 'K': v = group.keys
				elif type =='dV': v = group.dVerts[sub_index]
				elif type =='dN': v = group.dNorms[sub_index]
				elif type == 'T': v = group.tex_coords and group.tex_coords2
				if v:
					error( 'Error! List is not empty.' )
					error( 'Group: %i, Section index: %i, type: %s, sub_index: %i, element count: %i' % (len(DATA_GROUPS)-1, idx, type, sub_index, j) )
					return False
				v.extend(data)

		# again number of sections (?)
		j = unpack('<l', f.read(4))[0]
		assert j == i # ?

		# validate rigging data
		if group.bones and not group.weights:
			error( 'Error! Incorrect rigging data. (no weights)' )
			return False

		# validate morph data
		i = sum(2**i for i, v in enumerate(group.dVerts) if v)
		j = sum(2**j for j, v in enumerate(group.dNorms) if v)
		if i not in (0, 1, 3, 7, 15):
			error( 'Error! Invalid state of DiffVerts - %s' % format(i, '04b') )
			return False
		if j and j != i:
			error( 'Error! Invalid state of DiffNorms - %s (DiffVerts - %s)' % (format(j, '04b'), format(i, '04b')) )
			return False
		if i and not group.keys:
			error( 'Error! There are DiffVerts, but no DiffKeys in the group %i.' % (len(DATA_GROUPS)-1) )
			return False

		# index mapping
		#
		i = unpack('<l', f.read(4))[0]
		index_mapping1 = unpack('<%iH'%i, f.read(i*2))

		i = unpack('<l', f.read(4))[0]
		index_mapping2 = unpack('<%iH'%i, f.read(i*2))

		i = unpack('<l', f.read(4))[0]
		index_mapping3 = unpack('<%iH'%i, f.read(i*2))

		# apply indexing
		if index_mapping1: v =   group.vertices ; group.vertices   = [v[i] for i in index_mapping1]
		if index_mapping2: v =    group.normals ; group.normals    = [v[i] for i in index_mapping2]
		if index_mapping3: v = group.tex_coords ; group.tex_coords = [v[i] for i in index_mapping3]

		if index_mapping1 or index_mapping2 or index_mapping3:
			assert not (group.bones or group.keys)
			log( '--Index mapping: (%i, %i, %i)' % (len(index_mapping1), len(index_mapping2), len(index_mapping3)) )

		v = None

	#<-

	#
	# index groups (geometry parts)
	#

	log_level and log( '==INDICES===============================' )

	INDEX_GROUPS = []

	index_group_count = unpack('<l', f.read(4))[0]
	
	log_level and log( 'Number of index groups:', index_group_count )

	for k in xrange(index_group_count):

		log_level and log( 'Index group # %i @ %08x' % (k, f.tell()) )

		type, data_group_index = unpack('<2l', f.read(8))
		assert type == 2 # other primitives (if any), including 0-lines, are not supported

		log_level>1 and log( '--Refers to group:', data_group_index )

		# name
		name = read_str(f)
		log_level>1 and log( '--Name: "%s"' % name )

		# number of indices
		i = unpack('<l', f.read(4))[0]
		j = i*2
		assert i%3 == 0

		# add new index group
		group = IndexGroup(name) ; INDEX_GROUPS.append(group)
		group.data_group_index = data_group_index

		# read indices
		group.indices = chunk(unpack('<%iH'%i, f.read(j)), 3)

		log_level>1 and log( '--Number of indices: %i (%i triangles)' % (i, len(group.indices)) )

		# flags (?)
		s = f.read(4)
		log_level>1 and log( '--Flags (?):', to_hex(s) )
		group.flags = unpack('<L', s)[0]

		# bone indices (if any)
		i = unpack('<l', f.read(4))[0]
		if i != 0:
			s = f.read(i*2)
			group.bones = unpack('<%iH'%i, s)
			if log_level > 1:
				if i <= 5:
					log( '--Bone indices: %i' % i, group.bones )
				else:
					log( '--Bone indices: %i' % i, '(%i, %i, %i, %i, %i, ... )' % group.bones[:5] )
	#<-

	#
	# additional data
	#

	log_level and log( '==OTHER=================================' )

	# inverse transforms
	#
	k = unpack('<l', f.read(4))[0]
	if k:
		log_level and log( 'Inverse transforms (%i) @ %08x' % (k, f.tell()-4) )
		inverse_transforms = []
		for i in xrange(k):
			inverse_transforms.append( (unpack('<4f', f.read(16)), unpack('<3f', f.read(12))) )
	else:
		inverse_transforms = None

	# morphs
	#
	k = unpack('<l', f.read(4))[0]
	if k:
		log_level and log( 'Morphs / vertex animations (%i)' % k + (':' if log_level>1 else '') )
		MORPH_NAMES = []
		for i in xrange(k):
			v = (read_str(f), read_str(f))
			log_level>1 and log( '--Strings: "%s", "%s"' % v )
			MORPH_NAMES.append(v)
	else:
		MORPH_NAMES = None

	# static bounding mesh
	#
	i = unpack('<l', f.read(4))[0]
	if i:
		j = unpack('<l', f.read(4))[0]
		log_level and log( 'Static bounding mesh @ %08x' % (f.tell()-4) + (':' if log_level>1 else '') )
		if log_level > 1:
			log( '--Vertices:', i )
			log( '--Indices:', j )

		# read data
		V = chunk(unpack('<%if'%(i*3), f.read(i*12)), 3)
		I = chunk(unpack('<%iH'%j, f.read(j*2)), 3)
		static_bmesh = (V, I)
	else:
		static_bmesh = None

	# dynamic bounding mesh
	#
	i = unpack('<l', f.read(4))[0]
	if i:
		log_level and log( 'Dynamic bounding mesh parts (%i)' % i + (':' if log_level>1 else '') )
		dynamic_bmesh = []
		for k in xrange(i):
			offset = f.tell()
			i = unpack('<l', f.read(4))[0]
			if i:
				j = unpack('<l', f.read(4))[0]

				# read data
				V = chunk(unpack('<%if'%(i*3), f.read(i*12)), 3)
				I = chunk(unpack('<%iH'%j, f.read(j*2)), 3)
				dynamic_bmesh.append((V, I))

				log_level>1 and log( '--Part # %02i @ %08x -> vertices: %i, indices: %i' % (k, offset, len(V), len(I)) )
			else:
				dynamic_bmesh.append(None)

		if not any(dynamic_bmesh):
			dynamic_bmesh = None
	else:
		dynamic_bmesh = None

	log_level and log( '//// Finished @ %08x' % f.tell() )

	return GeometryData(DATA_GROUPS, INDEX_GROUPS, inverse_transforms, MORPH_NAMES, static_bmesh, dynamic_bmesh)


#-------------------------------------------------------------------------------

def _rm_doubles(geometry):

	for idx1, g1 in enumerate(geometry.data_groups):

		if g1.tex_coords:

			log( 'Processing data group # %i...' % idx1 )

			N = g1.normals or repeat(0)
			B = g1.bones   or repeat(0)
			W = g1.weights or repeat(0)
			K = g1.keys    or repeat(0)

			g1.mask = [] # remove deform mask

			# validate morph data
			#
			i = sum(2**i for i, v in enumerate(g1.dVerts) if v)
			j = sum(2**j for j, v in enumerate(g1.dNorms) if v)

			assert i in (0, 1, 3, 7, 15) and (j==0 or j==i) and (bool(i) == bool(g1.keys))

			dV = zip(*filter(bool, g1.dVerts)) or repeat(0)
			dN = zip(*filter(bool, g1.dNorms)) or repeat(0)

			unique_verts = {} # { vertex -> new_index }
			indices = [] # indices[old_index] -> new_index

			# search
			for vertex in zip(g1.vertices, N, B, W, K, dV, dN):
				k = unique_verts.setdefault(vertex, len(unique_verts))
				indices.append(k)
			assert len(indices) == g1.count

			unique_verts = [v for v, i in sorted(unique_verts.items(), key=lambda x: x[1])]

			log( '--Vertex count: %i -> %i' % (g1.count, len(unique_verts)) )
			log( '--Updating data...' )

			for idx2, g2 in enumerate(geometry.index_groups):

				if g2.data_group_index == idx1:

					log( '\x20\x20--Processing index group # %i...' % idx2 )

					I = g2.indices

					# move texture coords to index group
					T = g1.tex_coords
					g2.tex_coords = [(T[i], T[j], T[k]) for i, j, k in I]
					if g1.tex_coords2:
						T = g1.tex_coords2
						g2.tex_coords2 = [(T[i], T[j], T[k]) for i, j, k in I]

					# update indices
					g2.indices = [(indices[i], indices[j], indices[k]) for i, j, k in I]

					del T, I

			g1.count = len(unique_verts)
			g1.tex_coords = []
			g1.tex_coords2 = []
			g1.tangents = []

			g1.vertices, N, B, W, K, dV, dN = map(list, zip(*unique_verts))
			del unique_verts, indices

			# update data
			if g1.normals : g1.normals = N
			if g1.bones   : g1.bones   = B
			if g1.weights : g1.weights = W
			if g1.keys    : g1.keys    = K

			# pad with empty lists
			if any(g1.dVerts):
				dV = map(list, zip(*dV)) + [[], [], []]
				g1.dVerts = dV[:4]
			if any(g1.dNorms):
				dN = map(list, zip(*dN)) + [[], [], []]
				g1.dNorms = dN[:4]

			del N, B, W, K, dV, dN

	#<- data_groups


########################################
##  Exporter
########################################

def create_gmdc_file(filename, sg_resource_name, geometry):

	node = GeometryDataContainer(0)
	node.sg_resource_name = sg_resource_name
	node.geometry = geometry

	with open(filename, 'wb') as f:
		f.write(b'\x01\x00\xff\xff\x00\x00\x00\x00\x01\x00\x00\x00\x87\x86\x4F\xAC')
		node.write(f)

	del node


def _write_geometry_data(f, geometry):

	#
	# build sections
	#

	SECTIONS = []

	group_section_indices = [] # [group_index] -> (section_indices)

	for group in geometry.data_groups:
		indices = [len(SECTIONS)]
		SECTIONS.append(('V', 0, group.vertices))
		if group.normals:
			indices.append(len(SECTIONS))
			SECTIONS.append(('N', 0, group.normals))
		if group.tex_coords:
			indices.append(len(SECTIONS))
			SECTIONS.append(('T', 0, group.tex_coords))
			if group.tex_coords2:
				indices.append(len(SECTIONS))
				SECTIONS.append(('T', 1, group.tex_coords2))

		if group.bones:
			i = len(SECTIONS)
			indices+= [i, i+1]

			# align bone index tuples
			v = [(b + (0xff, 0xff, 0xff, 0xff))[:4] for b in group.bones]
			SECTIONS.append(('B', 0, v))

			# align bone weight tuples (length <= 3)
			k = min(3, max(map(len, group.weights)))
			v = [(w + (0.0, 0.0, 0.0))[:k] for w in group.weights]
			SECTIONS.append(('W', 0, v))

		if group.tangents:
			indices.append(len(SECTIONS))
			SECTIONS.append(('X', 0, group.tangents))

		if group.keys:
			# keys
			indices.append(len(SECTIONS))
			# get aligned key index tuples
			v = [(k + (0, 0, 0, 0))[:4] for k in group.keys]
			SECTIONS.append(('K', 0, v))

			# validate morph data
			i = sum(2**i for i, v in enumerate(group.dVerts) if v)
			j = sum(2**j for j, v in enumerate(group.dNorms) if v)

			assert i in (1, 3, 7, 15) and (j==0 or j==i)

			# dVerts
			k = sum(map(bool, group.dVerts))
			i = len(SECTIONS)
			indices+= range(i, i+k)
			for i in xrange(k):
				SECTIONS.append(('dV', i, group.dVerts[i]))

			# dNorms
			k = sum(map(bool, group.dNorms))
			i = len(SECTIONS)
			indices+= range(i, i+k)
			for i in xrange(k):
				SECTIONS.append(('dN', i, group.dNorms[i]))

		if group.mask:
			indices.append(len(SECTIONS))
			SECTIONS.append(('M', 0, group.mask))

		group_section_indices.append(tuple(indices))

	#
	# write sections
	#

	f.write(pack('<l', len(SECTIONS))) # number of sections

	for type, sub_index, data in SECTIONS:

		s = pack('<l', len(data)) # number of elements
		cc = len(data[0]) # component count

		# magic number
		if   type == 'V': s+= b'\x81\x07\x83\x5B'
		elif type == 'N': s+= b'\x8B\x07\x83\x3B'
		elif type == 'T': s+= b'\xAB\x07\x83\xBB'
		elif type == 'B': s+= b'\x11\x01\xD7\xFB'
		elif type == 'W': s+= b'\x05\x01\xD7\x3B'
		elif type == 'X': s+= b'\xA0\x2B\xD9\x89'
		elif type =='dV': s+= b'\xE1\xCF\xF2\x5C'
		elif type =='dN': s+= b'\x6A\x3A\x6F\xCB'
		elif type == 'K': s+= b'\xDC\xCF\xF2\xDC'
		elif type == 'M': s+= b'\x95\x07\x83\xDB'

		s+= pack('<l', sub_index)

		if type in ('B', 'K', 'M'):
			s+= b'\x04\x00\x00\x00' # 4 bytes
			s+= b'\x03\x00\x00\x00' # unknown
			s+= pack('<l', len(data)*4) # size in bytes
			fmt = '4B'
		else:
			s+= pack('<l', cc-1)    # floats (1, 2 or 3)
			s+= b'\x03\x00\x00\x00' # unknown
			s+= pack('<l', len(data)*4*cc) # size in bytes
			fmt = '<%if'%cc

		# header
		f.write(s)

		# data
		for t in data:
			f.write(pack(fmt, *t))

		f.write(b'\x00\x00\x00\x00') # no indices

	#
	# groups
	#

	# number of groups
	f.write(pack('<l', len(group_section_indices)))

	for t, group in zip(group_section_indices, geometry.data_groups):
		f.write(pack('<l', len(t)))         # number of sections
		f.write(pack('<%iH'%len(t), *t))    # section indices
		f.write(pack('<l', len(group.vertices))) # number of elements in section
		f.write(pack('<l', len(t)))         # again number of sections (?)
		f.write(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00') # no index mapping

	#
	# indices
	#

	# number of index groups
	f.write(pack('<l', len(geometry.index_groups)))

	for group in geometry.index_groups:
		f.write(b'\x02\x00\x00\x00') # triangles
		f.write(pack('<l', group.data_group_index))
		write_str(f, group.name)
		f.write(pack('<l', len(group.indices)*3))

		for t in group.indices:
			f.write(pack('<3H', *t))

		f.write(pack('<L', group.flags))

		if group.bones:
			f.write(pack('<l%iH'%len(group.bones), len(group.bones), *group.bones))
		else:
			f.write(b'\x00\x00\x00\x00') # no bones

	#
	# inverse transforms
	#

	if geometry.inverse_transforms:
		f.write(pack('<l', len(geometry.inverse_transforms)))
		for rot, loc in geometry.inverse_transforms:
			f.write(pack('<4f', *rot))
			f.write(pack('<3f', *loc))
	else:
		f.write(b'\x00\x00\x00\x00') # no transforms (static mesh)

	# morph names

	if geometry.morph_names:
		f.write(pack('<l', len(geometry.morph_names)))
		for name in geometry.morph_names:
			write_str(f, name[0])
			write_str(f, name[1])
	else:
		f.write(b'\x00\x00\x00\x00') # no morphs

	#
	# bounding geometry
	#

	# static

	if geometry.static_bmesh and geometry.static_bmesh[0]:
		V, I = geometry.static_bmesh
		f.write(pack('<l', len(V)))
		f.write(pack('<l', len(I)*3))

		for t in V:
			f.write(pack('<3f', *t))

		for t in I:
			f.write(pack('<3H', *t))
	else:
		f.write(b'\x00\x00\x00\x00')

	# dynamic

	if geometry.dynamic_bmesh:
		f.write(pack('<l', len(geometry.dynamic_bmesh)))
		for part in geometry.dynamic_bmesh:
			if part:
				V, I = part
				f.write(pack('<l', len(V)))
				f.write(pack('<l', len(I)*3))

				for t in V:
					f.write(pack('<3f', *t))

				for t in I:
					f.write(pack('<3H', *t))
			else:
				f.write(b'\x00\x00\x00\x00')
	else:
		f.write(b'\x00\x00\x00\x00')

