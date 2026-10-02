import os
import sys
import subprocess
import shutil


def build():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(project_dir, 'src')
    main_py = os.path.join(project_dir, 'main.py')
    dist_dir = os.path.join(project_dir, 'dist')
    build_dir = os.path.join(project_dir, 'build')
    
    # 清理旧的构建目录
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
    
    # PyInstaller 参数
    es_exe = os.path.join(project_dir, 'es.exe')
    args = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconsole',           # 无控制台窗口
        '--onefile',             # 单文件模式
        '--name', 'DuplicateCleaner',
        '--add-data', f'{src_dir};src',  # 包含源码目录
        '--add-binary', f'{es_exe};.',   # 将 es.exe 打包到根目录
        '--icon', os.path.join(project_dir, 'assets', 'icon.ico') if os.path.exists(os.path.join(project_dir, 'assets', 'icon.ico')) else 'NONE',
        '--clean',
        '--noconfirm',
        main_py
    ]
    
    # 移除不存在的图标参数
    if not os.path.exists(os.path.join(project_dir, 'assets', 'icon.ico')):
        args = [a for a in args if a != '--icon' and a != 'NONE']
    
    print("开始打包...")
    print(f"命令: {' '.join(args)}")
    
    result = subprocess.run(args, cwd=project_dir)
    
    if result.returncode == 0:
        exe_path = os.path.join(dist_dir, 'DuplicateCleaner.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n打包成功!")
            print(f"输出文件: {exe_path}")
            print(f"文件大小: {size_mb:.1f} MB")
        else:
            print("打包完成但未找到输出文件")
    else:
        print(f"\n打包失败，返回码: {result.returncode}")


if __name__ == '__main__':
    build()