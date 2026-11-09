import os, sys

lib_folder = os.path.join(os.path.dirname(__file__), 'libs')
sys.path.append(lib_folder)

import pythonnet

runtime = pythonnet.get_runtime_info()
if runtime is None:
	pythonnet.load('netfx')
elif runtime.kind != '.NET Framework':
	raise RuntimeError(
		"pandasnet requires pythonnet's .NET Framework runtime. "
		"Call pythonnet.load('netfx') before importing clr or pandasnet."
	)

import clr
clr.AddReference('PandasNet')

from PandasNet import Codecs
Codecs.Initialize(False)

from .conversion import wrap, wrap_class