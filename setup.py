from setuptools import setup, Command
import logging
import os
import shutil
import sys
import subprocess
import sysconfig

PY_MAJOR = sys.version_info[0]
PY_MINOR = sys.version_info[1]

CONFIGURED_PROPS = "configured.props"

def readme():
   with open('README.md', 'r', encoding='utf-8') as f:
       return f.read()


def _write_configure_props():
    defines = [
        f'PYTHON{PY_MAJOR}{PY_MINOR}'
    ]

    if sys.platform == 'win32':
        defines.append('WINDOWS')

    if hasattr(sys, "abiflags"):
        if "d" in sys.abiflags:
            defines.append("PYTHON_WITH_PYDEBUG")
        if "m" in sys.abiflags:
            defines.append("PYTHON_WITH_PYMALLOC")

    import xml.etree.ElementTree as ET

    proj = ET.Element("Project")
    props = ET.SubElement(proj, "PropertyGroup")
    c = ET.SubElement(props, "ConfiguredConstants")
    c.text = " ".join(defines)

    ET.ElementTree(proj).write(CONFIGURED_PROPS)


def _find_msbuild():
    msbuild = shutil.which('MSBuild.exe') or shutil.which('msbuild')
    if msbuild:
        return msbuild

    vswhere = os.path.join(
        os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
        'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    if os.path.exists(vswhere):
        result = subprocess.run(
            [vswhere, '-latest', '-products', '*', '-requires',
             'Microsoft.Component.MSBuild', '-find',
             r'MSBuild\Current\Bin\MSBuild.exe'],
            check=True, capture_output=True, text=True)
        msbuild = result.stdout.strip().splitlines()
        if msbuild:
            return msbuild[0]

    raise RuntimeError(
        'MSBuild.exe was not found. Install Visual Studio Build Tools with '
        'the .NET Framework targeting pack, or add MSBuild.exe to PATH.')


class configure(Command):
    """Configure command"""

    description = "Configure the pythonnet build"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.announce("Writing configured.props...", level=logging.INFO)
        _write_configure_props()


class DotnetLib:
    def __init__(self, name, path, **kwargs):
        self.name = name
        self.path = path
        self.args = kwargs


class build_dotnet(Command):
    """Build command for dotnet-cli based builds"""

    description = "Build DLLs with dotnet-cli"
    user_options = [
        ("dotnet-config", None, "dotnet build configuration"),
        (
            "inplace",
            "i",
            "ignore build-lib and put compiled extensions into the source "
            + "directory alongside your pure Python modules",
        ),
    ]

    def initialize_options(self):
        self.dotnet_config = None
        self.build_lib = None
        self.inplace = False

    def finalize_options(self):
        if self.dotnet_config is None:
            self.dotnet_config = "release"
        # self.dotnet_config = "debug"

        build = self.distribution.get_command_obj("build")
        build.ensure_finalized()
        if self.inplace:
            self.build_lib = "."
        else:
            self.build_lib = build.build_lib

    def run(self):
        dotnet_modules = self.distribution.dotnet_libs
        self.run_command("configure")

        for lib in dotnet_modules:
            output = os.path.join(
                os.path.abspath(self.build_lib), 
                lib.args.pop("output")
            )
            
            exclude = lib.args.pop("exclude", None)

            opts = sum([
                ["--" + name.replace("_", "-"), value] for name, value in lib.args.items()],
                [],
            )

            if sys.platform != 'win32':
                raise RuntimeError(
                    'Building pandasnet requires Windows and Visual Studio '
                    'MSBuild for the .NET Framework target.')

            output = os.path.abspath(output)
            self.announce("Running Visual Studio MSBuild...", level=logging.INFO)
            self.spawn([
                _find_msbuild(), lib.path,
                '/t:Build',
                '/p:Configuration=' + self.dotnet_config.capitalize(),
                '/p:OutputPath=' + output + os.sep,
                '/p:PythonNetRuntimePath=' + os.path.join(
                    sysconfig.get_path('purelib'), 'pythonnet', 'runtime',
                    'Python.Runtime.dll'),
            ])

            if exclude is not None:
                files = [os.path.join(output, f) for f in os.listdir(output) if exclude in f]
                [os.remove(f) for f in files if os.path.isfile(f)]


# Add build_dotnet to the build tasks:
from setuptools.command.build import build as _build
from setuptools.command.develop import develop as _develop
from setuptools import Distribution
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

class build(_build):
    sub_commands = _build.sub_commands + [("build_dotnet", None)]


class bdist_wheel(_bdist_wheel):
    """Tag the managed .NET Framework assembly with its Windows platform."""

    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, _, platform = super().get_tag()
        return "py3", "none", platform


class develop(_develop):
    def install_for_development(self):
        # Build extensions in-place
        self.reinitialize_command("build_dotnet", inplace=1)
        self.run_command("build_dotnet")

        return super().install_for_development()


# Monkey-patch Distribution s.t. it supports the dotnet_libs attribute
Distribution.dotnet_libs = None

cmdclass = {
    "build": build,
    "build_dotnet": build_dotnet,
    "bdist_wheel": bdist_wheel,
    "configure": configure,
    "develop": develop,
}

dotnet_libs = [
    DotnetLib(
        "pandas-converters",
        "dotnet/PandasNet/PandasNet.csproj",
        output="pandasnet/libs",
        exclude='Python.Runtime.'
    ),
    DotnetLib(
        "pandas-converters",
        "dotnet/PandasNet/PandasNet.csproj",
        output=os.path.join(os.path.dirname(__file__), "pandasnet/libs"),
        exclude='Python.Runtime.'
    ),
    DotnetLib(
        "pandas-converters-tests",
        "dotnet/LibForTests/LibForTests.csproj",
        output=os.path.join(os.path.dirname(__file__), 'tests/libs'),
    ),
]


setup(
    cmdclass=cmdclass,
    name='pandasnet',
    version='2.0.0',
    author='Fabien Dieulle',
    author_email='fabiendieulle@hotmail.fr',
    description='Extensions of pythonnet package to support pandas DataFrame conversions',
    long_description=readme(),
    long_description_content_type='text/markdown',
    url='https://github.com/fdieulle/pandasnet',
    packages=['pandasnet'],
    package_data={'pandasnet': ['libs/PandasNet.*']},
    install_requires=[
        'numpy>=2.0',
        'pandas>=3.0',
        'pythonnet>=3.2.0'],
    python_requires='>=3.11',
    dotnet_libs=dotnet_libs,
    classifiers=[
       "License :: OSI Approved :: MIT License",
        "Programming Language :: C#",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: Microsoft :: Windows",
    ],
    zip_safe=False
)