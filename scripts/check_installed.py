"""Check wheel installs from a fresh virtual environment, without source imports.

Run with that environment's Python and -I after installing all four wheels.
This does not build packages, install dependencies, or publish artifacts.
"""

import importlib
from importlib.metadata import distribution
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile


PACKAGES = ("benchguard", "datasetlint", "edgebench", "visioneval")
ROOT = Path(__file__).resolve().parents[1]


def main():
    if not sys.flags.isolated or sys.prefix == sys.base_prefix:
        raise RuntimeError("run with a fresh virtual environment's Python and -I")
    site = Path(sysconfig.get_path("purelib")).resolve()
    scripts = Path(sysconfig.get_path("scripts"))
    for name in PACKAGES:
        package = importlib.import_module(name)
        origin = Path(package.__file__).resolve()
        if not origin.is_relative_to(site):
            raise RuntimeError(f"{name} was not imported from this environment's site-packages")
        installed = distribution(name)
        entrypoints = [entry for entry in installed.entry_points
                       if entry.group == "console_scripts" and entry.name == name]
        if len(entrypoints) != 1:
            raise RuntimeError(f"{name} is missing its unique console entry point")
        print(f"{name} {installed.version}: installed import and entry point verified", flush=True)

    # Some existing tests spawn Python subprocesses without -I. Remove path
    # injection variables for those children as well, and use an empty cwd.
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"}}
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="benchguard-installed-") as cwd:
        for name in PACKAGES:
            suffix = ".exe" if os.name == "nt" else ""
            subprocess.run([str(scripts / (name + suffix)), "--help"],
                           cwd=cwd, env=env, check=True, timeout=30,
                           stdout=subprocess.DEVNULL)
        suites = [ROOT / "tests"]
        suites.extend(ROOT / "projects" / name / "tests" for name in PACKAGES[1:])
        suites.append(ROOT / "integration_tests")
        for suite in suites:
            print(f"Installed-package tests: {suite.relative_to(ROOT)}", flush=True)
            subprocess.run([sys.executable, "-I", "-m", "unittest", "discover",
                            "-s", str(suite), "-v"],
                           cwd=cwd, env=env, check=True, timeout=300)
    print("All installed-package checks passed", flush=True)


if __name__ == "__main__":
    main()
