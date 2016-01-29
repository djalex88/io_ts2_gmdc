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


__all__ = ['log', 'error', 'set_log_file', 'close_log_file', 'chunk', 'chain', 'repeat', 'to_hex', 'print_last_exception']

import sys
from itertools import chain, repeat

def set_log_file(f):
	global log_file
	log_file = f

def close_log_file():
	global log_file
	if log_file != None:
		log_file.close() ; log_file = None

def log(*args):
	s = '\x20'.join(str(x) for x in args)
	print s
	if log_file != None: print >> log_file, s

def error(*args):
	s = '\x20'.join(str(x) for x in args)
	print >> sys.stderr, s
	if log_file != None: print >> log_file, s

def to_hex(s):
	return '\x20'.join('%02X'%ord(x) for x in s)

def chunk(seq, sublen):
	return [seq[i:i+sublen] for i in xrange(0, len(seq), sublen)]

def print_last_exception():
	t, e, tb = sys.exc_info()
	error( repr(e) )
	i = 0
	while tb:
		c = tb.tb_frame.f_code
		error( '\x20\x20'*i + '--Function: "%s" in "%s", line: %i' % (c.co_name, c.co_filename, tb.tb_lineno) )
		tb = tb.tb_next ; i+= 1

log_file = None
