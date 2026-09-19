import subprocess
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


CREATE_NO_WINDOW = 0x08000000


@dataclass
class FileInfo:
    path: str
    name: str
    size: int
    modified_time: float
    created_time: float


def get_application_dir() -> str:
    """Get the directory where the application/executable is running from."""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe (PyInstaller)
        # For onefile mode, binaries are extracted to sys._MEIPASS
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


class EverythingSearch:
    def __init__(self, es_path: str = "es.exe"):
        # First try to use bundled es.exe in application directory
        app_dir = get_application_dir()
        bundled_es = os.path.join(app_dir, "es.exe")
        
        if os.path.isfile(bundled_es):
            self.es_path = bundled_es
        else:
            self.es_path = self._resolve_es_path(es_path)
        
        self._es_available = False
        self._es_version = ""
        self._verify_es()

    def _resolve_es_path(self, es_path: str) -> str:
        es_path = es_path.strip()
        if not es_path:
            return "es.exe"
        
        # If it's a full path, check if file exists
        if os.path.isfile(es_path):
            return os.path.abspath(es_path)
        
        # If it's just a filename, check in common locations
        if not os.path.dirname(es_path):
            common_paths = [
                os.path.join(os.environ.get("ProgramFiles", ""), "Everything", es_path),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Everything", es_path),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Everything", es_path),
            ]
            for p in common_paths:
                if os.path.isfile(p):
                    return p
        
        return es_path

    def _verify_es(self) -> bool:
        try:
            # Check if file exists first
            if not os.path.isfile(self.es_path) and not self._is_in_path(self.es_path):
                self._es_available = False
                self._es_version = f"文件不存在: {self.es_path}"
                return False
            
            # Verify it's actually es.exe by checking filename
            filename = os.path.basename(self.es_path).lower()
            if filename != "es.exe":
                self._es_available = False
                self._es_version = f"错误: 选择了 {filename}，需要 es.exe (命令行工具)，不是 Everything.exe (GUI程序)。\n请从 https://www.voidtools.com/downloads/ 下载 es.exe"
                return False
            
            result = subprocess.run([self.es_path, "-version"], capture_output=True, text=True, timeout=10, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0:
                self._es_available = True
                self._es_version = result.stdout.strip()
                return True
            else:
                stderr = result.stderr.strip() if result.stderr else "无错误输出"
                self._es_version = f"执行失败 (code={result.returncode}): {stderr}"
        except subprocess.TimeoutExpired:
            self._es_version = "执行超时 (10秒)"
        except FileNotFoundError:
            self._es_version = f"文件未找到: {self.es_path}"
        except OSError as e:
            self._es_version = f"系统错误: {str(e)}"
        except Exception as e:
            self._es_version = f"异常: {type(e).__name__}: {str(e)}"
        self._es_available = False
        return False

    def _is_in_path(self, executable: str) -> bool:
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            full_path = os.path.join(path_dir, executable)
            if os.path.isfile(full_path):
                return True
        return False

    def is_available(self) -> bool:
        return self._es_available

    def get_resolved_path(self) -> str:
        return self.es_path

    def get_version(self) -> str:
        return self._es_version

    def get_status_text(self) -> str:
        if self._es_available:
            return f"✓ 已连接 ({self._es_version}) - {self.es_path}"
        else:
            return f"✗ 未找到 es.exe (路径: {self.es_path})"

    def search_files(self, directory: str, min_size: int = 1) -> List[FileInfo]:
        directory = os.path.abspath(directory)
        
        results = []
        try:
            for root, dirs, files in os.walk(directory):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fp)
                        if min_size > 0 and size < min_size:
                            continue
                        if size <= 0:
                            continue
                        try:
                            stat = os.stat(fp)
                            mtime = stat.st_mtime
                            ctime = stat.st_ctime
                        except:
                            mtime = 0
                            ctime = 0
                        results.append(FileInfo(
                            path=fp,
                            name=f,
                            size=size,
                            modified_time=mtime,
                            created_time=ctime
                        ))
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] os.walk error: {e}")
            return []
        
        results.sort(key=lambda f: f.size)
        return results

    def search_files_multiple(self, directories: List[str], min_size: int = 1, progress_callback=None) -> List[FileInfo]:
        all_files = []
        total_dirs = len(directories)
        
        for i, directory in enumerate(directories):
            if progress_callback:
                progress_callback(i + 1, total_dirs, f"搜索目录 {i+1}/{total_dirs}: {directory}")
            
            files = self.search_files(directory, min_size)
            all_files.extend(files)
            
            # Validate against actual disk count
            try:
                disk_count = sum(len(files) for _, _, files in os.walk(directory))
                es_count = len(files)
                if disk_count > 0 and es_count < disk_count * 0.85:
                    msg = (f"⚠️ 索引可能不完整: {directory}\n"
                           f"   磁盘实际文件: {disk_count}, Everything 索引: {es_count}\n"
                           f"   建议在 Everything 中: 工具 → 强制重建数据库")
                    if progress_callback:
                        progress_callback(i + 1, total_dirs, msg)
                    print(f"[WARN] {msg}")
            except Exception:
                pass
        
        return all_files
    
    def reindex_everything(self) -> bool:
        """Force Everything to rebuild its database."""
        try:
            result = subprocess.run([self.es_path, "-reindex"], capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
            return result.returncode == 0
        except Exception as e:
            print(f"[ERROR] Reindex failed: {e}")
            return False

    def _parse_csv_output(self, csv_output: str) -> List[FileInfo]:
        lines = csv_output.strip().split('\n')
        if len(lines) < 2:
            return []
        
        files = []
        
        for line in lines[1:]:
            if not line.strip():
                continue
            # Use csv module for proper CSV parsing
            import csv
            from io import StringIO
            try:
                reader = csv.reader(StringIO(line))
                parts = next(reader)
            except Exception:
                # Fallback to simple split
                parts = line.split(',')
            
            if len(parts) < 4:
                continue
            
            try:
                path = parts[0].strip('"')
                size = int(parts[1]) if parts[1].isdigit() else 0
                
                # Parse date strings like "2026/9/7 17:49:11"
                def parse_datetime(date_str):
                    if not date_str:
                        return 0
                    try:
                        from datetime import datetime
                        # Try multiple formats
                        for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"]:
                            try:
                                return datetime.strptime(date_str.strip(), fmt).timestamp()
                            except ValueError:
                                continue
                    except Exception:
                        pass
                    return 0
                
                modified = parse_datetime(parts[2]) if len(parts) > 2 else 0
                created = parse_datetime(parts[3]) if len(parts) > 3 else 0
                
                # Skip directories - es.exe returns directories with recursive size,
                # which creates false size matches. Use os.path.isfile() to verify.
                if not os.path.isfile(path):
                    continue
                
                # Only add files with size > 0
                if size > 0:
                    files.append(FileInfo(
                        path=path,
                        name=os.path.basename(path),
                        size=size,
                        modified_time=modified,
                        created_time=created
                    ))
            except (ValueError, IndexError):
                continue
        
        return files

    def find_duplicates_by_size(self, directory: str, min_size: int = 1) -> Dict[int, List[FileInfo]]:
        files = self.search_files(directory, min_size)
        size_map: Dict[int, List[FileInfo]] = {}
        
        for f in files:
            if f.size not in size_map:
                size_map[f.size] = []
            size_map[f.size].append(f)
        
        return {k: v for k, v in size_map.items() if len(v) > 1}

    def find_duplicates_by_size_multiple(self, directories: List[str], min_size: int = 1, progress_callback=None) -> Dict[int, List[FileInfo]]:
        files = self.search_files_multiple(directories, min_size, progress_callback)
        size_map: Dict[int, List[FileInfo]] = {}
        
        for f in files:
            if f.size not in size_map:
                size_map[f.size] = []
            size_map[f.size].append(f)
        
        return {k: v for k, v in size_map.items() if len(v) > 1}