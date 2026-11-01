from pathlib import Path

from setuptools import setup, find_namespace_packages


README_PATH = Path(__file__).with_name("README.md")

setup(
    name="thonny-ai-assistant",
    version="0.6.2",
    description="Bilingual AI assistant plugin for Thonny",
    long_description=README_PATH.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="TommyLee2009",
    author_email="lcy28898830@gmail.com",
    license="MIT",
    license_files=["LICENSE"],
    packages=find_namespace_packages(
        include=["thonnycontrib", "thonnycontrib.*"],
    ),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Plugins",
        "Intended Audience :: Education",
        "Intended Audience :: Developers",
    ],
    install_requires=["openai>=1.75.0"],
    python_requires=">=3.8",
    platforms=["Windows", "macOS", "Linux"],
    keywords=[
        "thonny",
        "openai",
        "deepseek",
        "ai",
        "plugin",
        "ide",
        "education",
    ],
    # Thonny 插件命名空间
    entry_points={
        "thonny.plugins": [
            "thonny-ai-assistant = thonnycontrib.thonny_ai_assistant"
        ]
    }
)
