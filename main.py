#!/usr/bin/env python3
"""
重复文件清理工具
基于 Everything 快速搜索 + NTFS 硬链接替换重复文件
"""

import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ui.main_window import main

if __name__ == "__main__":
    main()