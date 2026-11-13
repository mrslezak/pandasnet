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
if not hasattr(clr, 'AddReference'):
	# IDE module reloaders (e.g. Spyder's UMR) drop pythonnet's clr module; clr.py cannot recreate it.
	clr = getattr(pythonnet, '_pandasnet_clr', None)
	if clr is None:
		raise RuntimeError(
			"pythonnet's clr module was removed from sys.modules after the .NET runtime started. "
			"Restart the Python process, or exclude clr/System/pandasnet from your IDE's module reloader."
		)
	sys.modules['clr'] = clr
# pythonnet is a library module, so reloaders keep it and the stashed clr survives.
pythonnet._pandasnet_clr = clr
clr.AddReference('PandasNet')

from PandasNet import Codecs
Codecs.Initialize(False)

from .conversion import wrap, wrap_class
from .auto import add_reference, load, unwrap
from .stubs import generate_stubs


def set_local_datetime_policy(policy: str) -> None:
	"""Choose how DateTimeKind.Local values are returned: 'wall_clock' (default) or 'utc'."""
	from PandasNet import LocalDateTimePolicy, Time

	policies = {'wall_clock': LocalDateTimePolicy.WallClock, 'utc': LocalDateTimePolicy.Utc}
	if policy not in policies:
		raise ValueError(f"policy must be one of {sorted(policies)}, not {policy!r}")
	Time.LocalPolicy = policies[policy]