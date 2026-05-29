import re
from pathlib import Path

from setuptools import find_packages, setup

_version_match = re.search(
    r'^__version__\s*=\s*["\']([^"\']+)["\']',
    Path("src/oma_switch/__init__.py").read_text(),
    re.MULTILINE,
)
if not _version_match:
    raise RuntimeError("Unable to find version string in src/oma_switch/__init__.py")

setup(
    name="oma-switch",
    version=_version_match.group(1),
    description="OMA (Oh-My-Agent) 配置文件切换工具 — 管理 opencode 的 oh-my-openagent.json 配置",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(where="src"),
    install_requires=["thefuzz[speedup]>=0.22.0"],
    package_dir={"": "src"},
    entry_points={
        "console_scripts": [
            "oma-switch=oma_switch.cli:main",
        ],
    },
)
