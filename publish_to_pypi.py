#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動打包並發布至 PyPI 的腳本
"""

import os
import re
import subprocess
import sys
import shutil
from pathlib import Path

def get_current_version(setup_file, pyproject_file):
    """從 setup.py 和 pyproject.toml 中提取目前的版本號"""
    setup_version = None
    pyproject_version = None
    
    # 從 setup.py 中提取版本號
    with open(setup_file, 'r', encoding='utf-8') as f:
        setup_content = f.read()
        version_match = re.search(r'version="([^"]+)"', setup_content)
        if version_match:
            setup_version = version_match.group(1)
    
    # 從 pyproject.toml 中提取版本號
    with open(pyproject_file, 'r', encoding='utf-8') as f:
        pyproject_content = f.read()
        version_match = re.search(r'version = "([^"]+)"', pyproject_content)
        if version_match:
            pyproject_version = version_match.group(1)
    
    # 檢查兩個文件中的版本號是否一致
    if setup_version and pyproject_version and setup_version != pyproject_version:
        print(f"警告: setup.py ({setup_version}) 和 pyproject.toml ({pyproject_version}) 中的版本號不一致")
        return setup_version  # 預設使用 setup.py 的版本號
    
    return setup_version or pyproject_version

def increment_version(version):
    """增加版本號"""
    if not version:
        return "0.1.0"
    
    parts = version.split('.')
    if len(parts) >= 3:
        parts[-1] = str(int(parts[-1]) + 1)
    else:
        parts.append('1')
    
    return '.'.join(parts)

def update_version_in_files(setup_file, pyproject_file, new_version):
    """在檔案中更新版本號"""
    files_updated = []
    
    # 更新 setup.py
    with open(setup_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(r'version="[^"]+"', f'version="{new_version}"', content)
    if new_content != content:
        with open(setup_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        files_updated.append(setup_file)
    
    # 更新 pyproject.toml
    with open(pyproject_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content)
    if new_content != content:
        with open(pyproject_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        files_updated.append(pyproject_file)
    
    return files_updated

def clean_build_directories():
    """清理舊的構建目錄和檔案"""
    dirs_to_clean = ['build', 'dist', '*.egg-info']
    
    for pattern in dirs_to_clean:
        if '*' in pattern:
            # 如果模式包含通配符，使用 glob
            import glob
            for item in glob.glob(pattern):
                if os.path.isdir(item):
                    print(f"清理目錄: {item}")
                    shutil.rmtree(item)
                elif os.path.exists(item):
                    print(f"刪除檔案: {item}")
                    os.remove(item)
        else:
            # 否則直接刪除目錄
            if os.path.isdir(pattern):
                print(f"清理目錄: {pattern}")
                shutil.rmtree(pattern)

def build_package():
    """使用 build 打包"""
    try:
        subprocess.run([sys.executable, "-m", "build"], check=True)
        return True
    except subprocess.CalledProcessError:
        print("打包失敗，請確認已安裝 build 套件: pip install build")
        return False

def upload_to_pypi(test=False):
    """使用 twine 上傳至 PyPI"""
    try:
        if test:
            subprocess.run(["twine", "upload", "--repository-url", "https://test.pypi.org/legacy/", "dist/*"], check=True)
        else:
            subprocess.run(["twine", "upload", "dist/*"], check=True)
        return True
    except subprocess.CalledProcessError:
        print("上傳失敗，請確認已安裝 twine 套件: pip install twine")
        return False

def check_egg_info_version(new_version):
    """檢查 egg-info 目錄中的版本資訊"""
    egg_dirs = [d for d in os.listdir('.') if d.endswith('.egg-info')]
    for egg_dir in egg_dirs:
        pkg_info_path = os.path.join(egg_dir, 'PKG-INFO')
        if os.path.exists(pkg_info_path):
            with open(pkg_info_path, 'r', encoding='utf-8') as f:
                content = f.read()
                version_match = re.search(r'Version: ([\d\.]+)', content)
                if version_match and version_match.group(1) != new_version:
                    print(f"警告: {pkg_info_path} 中的版本號 ({version_match.group(1)}) 與目標版本 ({new_version}) 不一致")
                    return False
    return True

def main():
    # 路徑設定
    current_dir = Path(__file__).parent.absolute()
    setup_file = current_dir / "setup.py"
    pyproject_file = current_dir / "pyproject.toml"
    
    # 檢查檔案是否存在
    if not setup_file.exists() or not pyproject_file.exists():
        print(f"錯誤: 無法找到 setup.py 或 pyproject.toml 檔案")
        return 1
    
    # 獲取當前版本號
    current_version = get_current_version(setup_file, pyproject_file)
    print(f"當前版本: {current_version}")
    
    # 累加版本號
    new_version = increment_version(current_version)
    print(f"新版本: {new_version}")
    
    # 詢問是否繼續
    confirm = input(f"確認將版本從 {current_version} 更新至 {new_version}? (y/N): ").lower()
    if confirm != 'y':
        print("操作已取消")
        return 0
    
    # 清理舊的構建目錄
    print("\n清理舊的構建目錄...")
    clean_build_directories()
    
    # 更新版本號
    updated_files = update_version_in_files(setup_file, pyproject_file, new_version)
    if updated_files:
        print(f"已更新版本號至 {new_version} 在以下檔案中:")
        for file in updated_files:
            print(f"  - {file}")
    else:
        print("沒有更新任何文件")
        return 1
    
    # 是否要上傳至測試版 PyPI
    use_test_pypi = input("是否上傳至測試版 PyPI? (y/N): ").lower() == 'y'
    
    # 打包
    print("\n開始打包...")
    if not build_package():
        return 1
    
    # 檢查 egg-info 目錄中的版本資訊
    if not check_egg_info_version(new_version):
        retry = input("版本號可能不一致，是否仍要繼續? (y/N): ").lower()
        if retry != 'y':
            print("操作已取消")
            return 1
    
    # 上傳
    print("\n開始上傳至 PyPI...")
    if not upload_to_pypi(test=use_test_pypi):
        return 1
    
    print(f"\n成功! 套件版本 {new_version} 已上傳至 {'測試版 ' if use_test_pypi else ''}PyPI")
    return 0

if __name__ == "__main__":
    sys.exit(main())