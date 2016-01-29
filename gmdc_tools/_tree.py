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


__all__ = ['Vector', 'Matrix', 'Quaternion', 'Transform', 'build_transform_tree']

########################################
##  Classes
########################################

class Vector(object):
	def __init__(self, x=0, y=0, z=0):
		self.x, self.y, self.z = float(x), float(y), float(z)

	def __add__(self, v):
		return Vector(self.x+v.x, self.y+v.y, self.z+v.z)
	def __sub__(self, v):
		return Vector(self.x-v.x, self.y-v.y, self.z-v.z)
	def __mul__(self, x):
		return self.dot(x) if isinstance(x, type(self)) else Vector(self.x*x, self.y*x, self.z*x)
	def __str__(self):
		return 'v(%s)' % ", ".join(str(round(x, 6) or 0.0) for x in self)
	def __repr__(self):
		return self.__str__()
	def __iter__(self):
		return iter(self.to_tuple())

	def len(self):
		return (self.x**2 + self.y**2 + self.z**2)**0.5

	def dot(self, v):
		return self.x*v.x + self.y*v.y + self.z*v.z

	def cross(self, v):
		return Vector(self.y*v.z-self.z*v.y, self.z*v.x-self.x*v.z, self.x*v.y-self.y*v.x)

	def to_tuple(self):
		return (self.x, self.y, self.z)

class Matrix(object):
	def __init__(self,
		##---------- X    Y    Z
			row1 = (1.0, 0.0, 0.0),
			row2 = (0.0, 1.0, 0.0),
			row3 = (0.0, 0.0, 1.0)):

		self._m = [(None,)*4, [None]+list(row1), [None]+list(row2), [None]+list(row3)]

	def row(self, i):
		if i not in (1,2,3): raise KeyError(i)
		return Vector(*self._m[i][1:])
	def col(self, i):
		if i not in (1,2,3): raise KeyError(i)
		return Vector(*(row[i] for row in self._m[1:]))

	def __mul__(A, B):
		C = Matrix()
		for i in (1, 2, 3):
			for j in (1, 2, 3):
				C[i,j] = A.row(i)*B.col(j)
		return C

	def det(self):
		return self.row(1) * self.row(2).cross(self.row(3))

	def get_inverse(self):
		det = self.det()
		if round(det, 8) == 0.0: return Matrix()
		X, Y, Z = (self.col(i) for i in (1, 2, 3))
		inv_det = 1./det
		return Matrix(Y.cross(Z)*inv_det, Z.cross(X)*inv_det, X.cross(Y)*inv_det)

	def transformVector(self, v):
		return Vector(*(self.row(i).dot(v) for i in (1, 2, 3)))

	def __str__(self):
		rows = [tuple(str(round(x, 6) or 0.0) for x in self._m[i][1:]) for i in (1, 2, 3)]
		fmt = ", ".join('%'+str(max(map(len, c)))+'s' for c in zip(*rows))
		rows = tuple(fmt % r for r in rows)
		s = '\x2f %s \x5c\n\x7c %s \x7c\n\x5c %s \x2f' % rows
		return s
	def __repr__(self):
		return self.__str__()

	def __getitem__(self, ij):
		i, j = ij
		if i not in (1,2,3) or j not in (1,2,3): raise KeyError(ij)
		return self._m[i][j]
	def __setitem__(self, ij, x):
		i, j = ij
		if i not in (1,2,3) or j not in (1,2,3): raise KeyError(ij)
		self._m[i][j] = x

class Quaternion(object):
	def __init__(self, x=0, y=0, z=0, w=1):
		self.x, self.y, self.z, self.w = float(x), float(y), float(z), float(w)

	def get_inverse(self):
		s = self.x**2 + self.y**2 + self.z**2 + self.w**2
		return Quaternion( -self.x/s, -self.y/s, -self.z/s, self.w/s )

	def get_matrix(self):
		x, y, z, w = self.x, self.y, self.z, self.w
		m = Matrix()

		m[1,1] = 1 - 2*(y*y + z*z)
		m[2,1] = 2*(x*y + w*z)
		m[3,1] = 2*(x*z - w*y)

		m[1,2] = 2*(x*y - w*z)
		m[2,2] = 1 - 2*(x*x + z*z)
		m[3,2] = 2*(y*z + w*x)

		m[1,3] = 2*(x*z + w*y)
		m[2,3] = 2*(y*z - w*x)
		m[3,3] = 1 - 2*(x*x + y*y)

		return m

	def __mul__(self, q):
		x, y, z, w = self.x, self.y, self.z, self.w
		return Quaternion(
			w*q.x + x*q.w + y*q.z - z*q.y,
			w*q.y + y*q.w + z*q.x - x*q.z,
			w*q.z + z*q.w + x*q.y - y*q.x,
			w*q.w - x*q.x - y*q.y - z*q.z )

	def __str__(self):
		return 'q(%s)' % ", ".join(str(round(x, 6) or 0.0) for x in self)
	def __repr__(self):
		return self.__str__()
	def __iter__(self):
		return iter(self.to_tuple())

	def to_tuple(self):
		return (self.x, self.y, self.z, self.w)

class Transform(object):
	def __init__(self, loc=(0.,0.,0.), rot=(0.,0.,0.,1.)):
		self.loc, self.rot = Vector(*loc), Quaternion(*rot)

	def transformPoint(self, p):
		return self.rot.get_matrix().transformVector(p) + self.loc

	def get_inverse(self):
		rot = self.rot.get_inverse()
		loc = rot.get_matrix().transformVector(self.loc*(-1.0))
		return Transform(loc, rot)

	def __mul__(self, t):
		return Transform(self.transformPoint(t.loc), self.rot*t.rot)

	def __str__(self):
		s = 'Transform\n'
		s+= '-translation: ' + str(self.loc) + '\n'
		s+= '-rotation: ' + str(self.rot) + '\n'
		s+= str(self.rot.get_matrix())
		return s
	def __repr__(self):
		return self.__str__()

class _myTransformTreeNode(object):
	def __init__(self, loc, rot, type='Transform', child_nodes=None, name=None, bone_index=None):
		self.transform = Transform(loc, rot)
		self.parent = None
		self.child_nodes = child_nodes
		self.abs_transform = None
		if self.child_nodes:
			for node in self.child_nodes:
				node.parent = self
		self.type = type
		self.name = name
		self.bone_index = bone_index

	def __str__(self):
		s = '<%s>\x20'%self.type if self.type!='Transform' else ''
		s+= '"%s"' % self.name if self.name else '(unnamed)'
		s+= '\x20(#%i):\x20'%self.bone_index if self.bone_index!=None else ':\x20'
		s+= str(self.transform.loc) + '\x20' + str(self.transform.rot)
		return s
	def __repr__(self):
		return self.__str__()

class _myTransformTree(object):
	def __init__(self):
		self.root_nodes = None
		self._dict = dict()

	@staticmethod
	def _str_subtree(nodes, indent=''):
		s = ''
		for node in nodes:
			s+= '\n' + indent + str(node)
			if node.child_nodes:
				s+= _myTransformTree._str_subtree(node.child_nodes, indent+'\x20\x20')
		return s
	def __str__(self):
		s = 'TransformTree' + _myTransformTree._str_subtree(self.root_nodes, '\x20\x20')
		return s
	def __repr__(self):
		return self.__str__()

	@staticmethod
	def _calc_abs_trans(nodes, basis=Transform()):
		for node in nodes:
			node.abs_transform = basis * node.transform
			_myTransformTree._calc_abs_trans(node.child_nodes, node.abs_transform)

	@staticmethod
	def _iter_nodes(nodes):
		for node in nodes:
			yield node
			for desc_node in _myTransformTree._iter_nodes(node.child_nodes):
				yield desc_node
	def __iter__(self):
		return _myTransformTree._iter_nodes(self.root_nodes)

	def get_node(self, key):
		return self._dict[key]


#-------------------------------------------------------------------------------

def build_transform_tree(sg_nodes):

	possible_nodes = {
		'cTransformNode' : 'Transform', 'cShapeRefNode' : 'ShapeRef', 'cLightRefNode' : 'LightRef',
		'cViewerRefNode' : 'ViewerRef', 'cViewerRefNodeRecursive' : 'ViewerRefRecursive' }

	def add_to_dict(dict, key, x):
		try:
			dict[key]+= (x,)
		except KeyError:
			dict[key] = x
		except:
			dict[key] = (dict[key], x)

	def build_tree_nodes(indices):

		nodes = [sg_nodes[i] for i in indices]
		assert all(map(lambda node: node.type in possible_nodes, nodes))

		index_lists = [[i for b1, b2, i in node.child_nodes] for node in nodes]

		tree_nodes = []
		for node, indices in zip(nodes, index_lists):

			t_node = _myTransformTreeNode(
						loc         = node.T_loc,
						rot         = node.T_rot,
						type        = possible_nodes[node.type],
						name        = node.obj_string,
						bone_index  = node.T_bone_index,
						child_nodes = build_tree_nodes(indices) )

			tree_nodes.append(t_node)

			node.T_bone_index != None and \
			add_to_dict(tree._dict, node.T_bone_index, t_node)
			add_to_dict(tree._dict, node.  obj_string, t_node)

		return tree_nodes

	resource_node = sg_nodes[0]
	assert resource_node.type == 'cResourceNode'

	tree = _myTransformTree()
	tree.root_nodes = build_tree_nodes([i for b1, b2, i in resource_node.child_nodes])
	tree._calc_abs_trans(tree.root_nodes)

	return tree

