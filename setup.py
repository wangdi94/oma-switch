from setuptools import setup, find_packages

setup(
    name="oma-switch",
    version="2.1.0",
    description="OMA (Oh-My-Agent) 配置文件切换工具 — 管理 opencode 的 oh-my-openagent.json 配置",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    entry_points={
        "console_scripts": [
            "oma-switch=oma_switch.cli:main",
        ],
    },
)
