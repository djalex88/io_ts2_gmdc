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

from struct import pack, unpack
from _common import *

########################################
##  Base node class
########################################

class _SGNode(object):
	# General properties:
	# - index
	# - type
	# - version
	# cResourceNode:
	# - Res_unknown (5 bytes)
	# cSGResource:
	# - sg_resource_name
	# cCompositionTreeNode:
	# - child_nodes
	# cObjectGraphNode:
	# - extensions
	# - obj_string
	# cRenderableNode:
	# - R_number1 (ushort)
	# - R_number2 (long)
	# - R_strings
	# - R_unknown (5 bytes)
	# cTransformNode:
	# - T_loc
	# - T_rot
	# - T_bone_index
	# cDataListExtension:
	# - Ext_data
	# cShapeRefNode:
	# - SR_data1
	# - SR_unknown1 (4 bytes)
	# - SR_data2
	# - SR_strings (version 0x15)
	# - SR_unknown2 (8 bytes)
	# cLightRefNode:
	# - L_index (BBl)
	# - L_unknown (2 bytes)
	# cBoneDataExtension:
	# - B_ext_unknown (12 bytes)
	# - B_ext_float
	# - B_ext_quat
	# cViewerRefNode:
	# - V_data
	# cViewerRefNodeRecursive:
	# - VR_unknown (1 bytes)
	# - VR_string
	# - VR_data (64 bytes)
	# cGeometryNode:
	# - G_unknown (7 bytes)
	# cGeometryDataContainer
	# - geometry
	#

	def __init__(self, index):
		self.index = index
		self.type = None

	def __str__(self):
		return 'unknown'

	def __repr__(self):
		return self.__str__()

	#
	# _read_-methods
	#

	def _read_cSGResource(self, f):
		s = f.read(20)
		if s != '\x0bcSGResource\x00\x00\x00\x00\x02\x00\x00\x00':
			error( 'Error! cSGResource header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		self.sg_resource_name = f.read(ord(f.read(1)))
		return True

	def _read_cCompositionTreeNode(self, f):
		s = f.read(29)
		if s != '\x14cCompositionTreeNode\x00\x00\x00\x00\x0b\x00\x00\x00':
			error( 'Error! cCompositionTreeNode header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		if not self._read_cObjectGraphNode(f): return False
		i = unpack('<l', f.read(4))[0]
		s = f.read(i*6)
		v = unpack('<'+'BBl'*(len(s)/6), s)
		self.child_nodes = chunk(v, 3)
		return True

	def _read_cObjectGraphNode(self, f):
		s = f.read(25)
		if s != '\x10cObjectGraphNode\x00\x00\x00\x00\x04\x00\x00\x00':
			error( 'Error! cObjectGraphNode header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		i = unpack('<l', f.read(4))[0]
		s = f.read(i*6)
		v = unpack('<'+'BBl'*(len(s)/6), s)
		self.extensions = chunk(v, 3)
		self.obj_string = f.read(ord(f.read(1)))
		return True

	def _read_cRenderableNode(self, f):
		s = f.read(24)
		if s != '\x0fcRenderableNode\x00\x00\x00\x00\x05\x00\x00\x00':
			error( 'Error! cRenderableNode header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		if not self._read_cBoundedNode(f): return False
		i, j = unpack('<Hl', f.read(6))
		self.R_number1 = i
		self.R_number2 = j
		v = []
		while j:
			v.append(f.read(ord(f.read(1)))) # such as 'Practical', 'Sims', etc.
			j-= 1
		self.R_strings = v
		self.R_unknown = f.read(5)
		return True

	def _read_cBoundedNode(self, f):
		s = f.read(21)
		if s != '\x0ccBoundedNode\x00\x00\x00\x00\x05\x00\x00\x00':
			error( 'Error! cBoundedNode header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		return self._read_cTransformNode(f)

	def _read_cTransformNode(self, f):
		s = f.read(23)
		if s != '\x0ecTransformNode\x62\x64\x24\x65\x07\x00\x00\x00':
			error( 'Error! cTransformNode header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		if not self._read_cCompositionTreeNode(f): return False
		self.T_loc = unpack('<3f', f.read(12))
		self.T_rot = unpack('<4f', f.read(16))
		i = unpack('<l', f.read(4))[0]
		self.T_bone_index = i if i!=0x7fffffff else None
		return True

	def _read_cExtension_h(self, f):
		s = f.read(19)
		if s != '\x0acExtension\x00\x00\x00\x00\x03\x00\x00\x00':
			error( 'Error! cExtension header:', to_hex(s) )
			error( '%#x' % f.tell() )
			return False
		return True

	#
	# _write_-methods
	#

	def _write_cSGResource(self, f):
		f.write('\x0bcSGResource\x00\x00\x00\x00\x02\x00\x00\x00')
		f.write(chr(len(self.sg_resource_name)) + self.sg_resource_name)

	def _write_cCompositionTreeNode(self, f):
		f.write('\x14cCompositionTreeNode\x00\x00\x00\x00\x0b\x00\x00\x00')
		self._write_cObjectGraphNode(f)
		f.write(pack('<l', len(self.child_nodes)))
		for t in self.child_nodes:
			f.write(pack('<BBl', *t))

	def _write_cObjectGraphNode(self, f):
		f.write('\x10cObjectGraphNode\x00\x00\x00\x00\x04\x00\x00\x00')
		f.write(pack('<l', len(self.extensions)))
		for t in self.extensions:
			f.write(pack('<BBl', *t))
		f.write(chr(len(self.obj_string)) + self.obj_string)

	def _write_cRenderableNode(self, f):
		f.write('\x0fcRenderableNode\x00\x00\x00\x00\x05\x00\x00\x00')
		self._write_cBoundedNode(f)
		f.write(pack('<Hl', self.R_number1, self.R_number2))
		assert self.R_number2 == len(self.R_strings)
		for s in self.R_strings:
			f.write(chr(len(s)) + s)
		f.write(self.R_unknown)

	def _write_cBoundedNode(self, f):
		f.write('\x0ccBoundedNode\x00\x00\x00\x00\x05\x00\x00\x00')
		self._write_cTransformNode(f)

	def _write_cTransformNode(self, f):
		f.write('\x0ecTransformNode\x62\x64\x24\x65\x07\x00\x00\x00')
		self._write_cCompositionTreeNode(f)
		f.write(pack('<3f', *self.T_loc) + pack('<4f', *self.T_rot))
		f.write('\xff\xff\xff\x7f' if self.T_bone_index is None else pack('<l', self.T_bone_index))

	def _write_cExtension_h(self, f):
		f.write('\x0acExtension\x00\x00\x00\x00\x03\x00\x00\x00')

	#
	# _str_-methods
	#

	def _str_cSGResource(self):
		return '--SGResource: "%s"' % self.sg_resource_name

	def _str_cCompositionTreeNode(self):
		s = self._str_cObjectGraphNode()
		s+= '\n'.join(['\n--Child nodes (%i):' % len(self.child_nodes)] + ['\x20\x20(%i, %i, %i)' % t for t in self.child_nodes])
		return s

	def _str_cObjectGraphNode(self):
		s = '--Extensions (%i):\n' % len(self.extensions)
		s+= "".join('\x20\x20(%i, %i, %i)\n' % t for t in self.extensions)
		s+= '--String: "%s"' % self.obj_string
		return s

	def _str_cRenderableNode(self):
		s = '_R{\n' + self._str_cBoundedNode() + '\n'
		s+= '--Numbers: (%i, %i)\n' % (self.R_number1, self.R_number2)
		s+= '--Strings: ' + str(self.R_strings) + '\n'
		s+= '--Unknown: ' + to_hex(self.R_unknown) + '\n}R_'
		return s

	def _str_cBoundedNode(self):
		return '_B{\n' + self._str_cTransformNode() + '\n}B_'

	def _str_cTransformNode(self):
		s = 'cTransformNode\n' + self._str_cCompositionTreeNode() + '\n'
		s+= '--Transform: (%f, %f, %f) ' % self.T_loc + '(%f, %f, %f, %f)\n' % self.T_rot
		s+= '--Bone index: ' + str(self.T_bone_index)
		return s

#<- /_SGNode
