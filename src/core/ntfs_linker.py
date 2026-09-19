import os
import ctypes
import uuid
import tempfile
import glob
from ctypes import wintypes
import win32com.client
from pathlib import Path
from typing import Optional, Tuple
from enum import Enum


FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOF_NORECURSION = 0x1000


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.UINT),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class LinkType(Enum):
    HARD_LINK = "hard_link"
    SYMBOLIC_LINK = "symbolic_link"
    JUNCTION = "junction"


class NTFSLinker:
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        self.shell32 = ctypes.windll.shell32
        self._setup_functions()

    def _setup_functions(self):
        self.kernel32.CreateHardLinkW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPVOID]
        self.kernel32.CreateHardLinkW.restype = ctypes.wintypes.BOOL
        
        self.kernel32.CreateSymbolicLinkW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD]
        self.kernel32.CreateSymbolicLinkW.restype = ctypes.wintypes.BOOL
        
        self.kernel32.DeleteFileW.argtypes = [ctypes.wintypes.LPCWSTR]
        self.kernel32.DeleteFileW.restype = ctypes.wintypes.BOOL
        
        self.kernel32.GetFileAttributesW.argtypes = [ctypes.wintypes.LPCWSTR]
        self.kernel32.GetFileAttributesW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        
        self.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFileInformationByHandle.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL

        self.kernel32.GetFinalPathNameByHandleW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        
        self.shell32 = ctypes.windll.shell32
        self.shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
        self.shell32.SHFileOperationW.restype = ctypes.c_int

    def get_hard_link_count(self, file_path: str) -> int:
        try:
            file_path = os.path.abspath(file_path)
            GENERIC_READ = 0x80000000
            FILE_SHARE_READ = 0x1
            FILE_SHARE_WRITE = 0x2
            FILE_SHARE_DELETE = 0x4
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = -1
            
            handle = self.kernel32.CreateFileW(
                file_path, GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
            )
            if handle == -1 or handle == 0xFFFFFFFFFFFFFFFF:
                return 1
            
            class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("dwFileAttributes", wintypes.DWORD),
                    ("ftCreationTime", wintypes.FILETIME),
                    ("ftLastAccessTime", wintypes.FILETIME),
                    ("ftLastWriteTime", wintypes.FILETIME),
                    ("dwVolumeSerialNumber", wintypes.DWORD),
                    ("nFileSizeHigh", wintypes.DWORD),
                    ("nFileSizeLow", wintypes.DWORD),
                    ("nNumberOfLinks", wintypes.DWORD),
                    ("nFileIndexHigh", wintypes.DWORD),
                    ("nFileIndexLow", wintypes.DWORD),
                ]
            
            info = BY_HANDLE_FILE_INFORMATION()
            success = self.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info))
            self.kernel32.CloseHandle(handle)
            
            if success:
                return info.nNumberOfLinks
            return 1
        except Exception:
            return 1

    def get_file_index(self, file_path: str) -> Optional[Tuple[int, int, int]]:
        """
        Return (volume_serial, file_index_high, file_index_low) for a file.
        Two hard links to the same file share the same (volume_serial, file_index_high, file_index_low).
        Returns None on failure.
        """
        try:
            file_path = os.path.abspath(file_path)
            GENERIC_READ = 0x80000000
            FILE_SHARE_READ = 0x1
            FILE_SHARE_WRITE = 0x2
            FILE_SHARE_DELETE = 0x4
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = -1
            
            handle = self.kernel32.CreateFileW(
                file_path, GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
            )
            if handle == -1 or handle == 0xFFFFFFFFFFFFFFFF:
                return None
            
            class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("dwFileAttributes", wintypes.DWORD),
                    ("ftCreationTime", wintypes.FILETIME),
                    ("ftLastAccessTime", wintypes.FILETIME),
                    ("ftLastWriteTime", wintypes.FILETIME),
                    ("dwVolumeSerialNumber", wintypes.DWORD),
                    ("nFileSizeHigh", wintypes.DWORD),
                    ("nFileSizeLow", wintypes.DWORD),
                    ("nNumberOfLinks", wintypes.DWORD),
                    ("nFileIndexHigh", wintypes.DWORD),
                    ("nFileIndexLow", wintypes.DWORD),
                ]
            
            info = BY_HANDLE_FILE_INFORMATION()
            success = self.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info))
            self.kernel32.CloseHandle(handle)
            
            if success:
                return (info.dwVolumeSerialNumber, info.nFileIndexHigh, info.nFileIndexLow)
            return None
        except Exception:
            return None

    def create_hard_link(self, link_path: str, target_path: str) -> Tuple[bool, str]:
        try:
            link_path = os.path.abspath(link_path)
            target_path = os.path.abspath(target_path)
            
            if not os.path.exists(target_path):
                return False, f"目标文件不存在: {target_path}"
            
            if os.path.exists(link_path):
                return False, f"链接路径已存在: {link_path}"
            
            link_dir = os.path.dirname(link_path)
            if not os.path.exists(link_dir):
                os.makedirs(link_dir, exist_ok=True)
            
            result = self.kernel32.CreateHardLinkW(link_path, target_path, None)
            if result:
                return True, "硬链接创建成功"
            else:
                error_code = ctypes.GetLastError()
                return False, f"创建硬链接失败，错误代码: {error_code}"
        except Exception as e:
            return False, f"创建硬链接异常: {str(e)}"

    def create_symbolic_link(self, link_path: str, target_path: str, is_directory: bool = False) -> Tuple[bool, str]:
        try:
            link_path = os.path.abspath(link_path)
            target_path = os.path.abspath(target_path)
            
            if os.path.exists(link_path):
                return False, f"链接路径已存在: {link_path}"
            
            link_dir = os.path.dirname(link_path)
            if not os.path.exists(link_dir):
                os.makedirs(link_dir, exist_ok=True)
            
            # 先检查文件系统是否支持符号链接
            if not self._check_fs_supports_symlinks(link_path):
                return self._create_hard_link_fallback(link_path, target_path)
            
            flags = 0x1 if is_directory else 0x0
            result = self.kernel32.CreateSymbolicLinkW(link_path, target_path, 0x1 if is_directory else 0x0)
            if result:
                return True, "符号链接创建成功"
            else:
                error_code = ctypes.GetLastError()
                if error_code == 1314:  # ERROR_PRIVILEGE_NOT_HELD
                    return self._create_hard_link_fallback(link_path, target_path)
                elif error_code == 1310:  # ERROR_NOT_SUPPORTED
                    return self._create_hard_link_fallback(link_path, target_path)
                else:
                    return False, f"创建符号链接失败，错误代码: {error_code}"
        except Exception as e:
            return False, f"创建符号链接异常: {str(e)}"

    def _check_fs_supports_symlinks(self, path: str) -> bool:
        """检查文件系统是否支持符号链接"""
        try:
            path = os.path.abspath(path)
            root = os.path.splitdrive(path)[0] + '\\'
            if not root or root == ':\\':
                root = path
            
            fs_flags = ctypes.c_ulong(0)
            success = self.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(path),
                None, 0,
                None, None,
                ctypes.byref(ctypes.c_ulong(0)),
                None, 0
            )
            if not success:
                return False
            
            # 通过尝试创建一个临时符号链接来测试
            import tempfile
            import uuid
            test_dir = tempfile.gettempdir()
            test_link = os.path.join(tempfile.gettempdir(), f"test_symlink_{uuid.uuid4().hex}.tmp")
            test_target = os.path.join(tempfile.gettempdir(), "test_target.txt")
            
            try:
                with open(os.path.join(tempfile.gettempdir(), "test_target.txt"), 'w') as f:
                    f.write("test")
                flags = 0x0
                result = self.kernel32.CreateSymbolicLinkW(
                    os.path.join(tempfile.gettempdir(), f"test_symlink_{uuid.uuid4().hex}.tmp"),
                    os.path.join(tempfile.gettempdir(), "test_target.txt"), 
                    0
                )
                if result:
                    os.remove(os.path.join(tempfile.gettempdir(), f"test_symlink_{uuid.uuid4().hex}.tmp"))
                    os.remove(os.path.join(tempfile.gettempdir(), "test_target.txt"))
                    return True
            except Exception:
                pass
            return False
        except Exception:
            return False

    def _create_hard_link_fallback(self, link_path: str, target_path: str) -> Tuple[bool, str]:
        """当符号链接不支持时，尝试创建硬链接作为后备"""
        try:
            link_path = os.path.abspath(link_path)
            target_path = os.path.abspath(target_path)
            
            if not os.path.exists(target_path):
                return False, f"目标文件不存在: {target_path}"
            
            if os.path.exists(link_path):
                return False, f"链接路径已存在: {link_path}"
            
            link_dir = os.path.dirname(link_path)
            if not os.path.exists(link_dir):
                os.makedirs(link_dir, exist_ok=True)
            
            result = self.kernel32.CreateHardLinkW(link_path, target_path, None)
            if result:
                return True, "已创建硬链接（文件系统不支持符号链接，已回退到硬链接）"
            else:
                error_code = ctypes.GetLastError()
                return False, f"创建硬链接失败，错误代码: {ctypes.GetLastError()}"
        except Exception as e:
            return False, f"创建硬链接后备方案异常: {str(e)}"
        
    def move_to_recycle_bin(self, file_path: str) -> Tuple[bool, str]:
        try:
            file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                return False, f"文件不存在: {file_path}"
            
            from_buffer = ctypes.create_unicode_buffer(file_path + "\0\0")
            operation = SHFILEOPSTRUCTW()
            operation.hwnd = None
            operation.wFunc = FO_DELETE
            operation.pFrom = ctypes.cast(from_buffer, wintypes.LPCWSTR)
            operation.pTo = None
            operation.fFlags = 0x0040 | 0x0004 | 0x0010 | 0x0400 | 0x1000  # FOF_ALLOWUNDO | FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_NORECURSION
            
            result = self.shell32.SHFileOperationW(ctypes.byref(operation))
            if result != 0:
                return False, f"移入回收站失败，错误代码: {result}"
            if operation.fAnyOperationsAborted:
                return False, "移入回收站操作已取消"
            if os.path.exists(file_path):
                return False, "移入回收站后文件仍存在"
            if not self._is_in_recycle_bin(file_path):
                return False, "文件已消失但未在回收站中找到，可能被永久删除"
            return True, "已移入回收站"
        except Exception as e:
            return False, f"移入回收站异常: {str(e)}"

    def _is_in_recycle_bin(self, file_path: str) -> bool:
        try:
            file_name = os.path.basename(file_path)
            shell = win32com.client.Dispatch('Shell.Application')
            recycle = shell.Namespace(10)
            if not recycle:
                return False
            for item in recycle.Items():
                try:
                    if item.Name == file_name:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def replace_with_symlink(self, duplicate_path: str, original_path: str) -> Tuple[bool, str]:
        try:
            duplicate_path = os.path.abspath(duplicate_path)
            original_path = os.path.abspath(original_path)
            
            if not os.path.exists(original_path):
                return False, f"原始文件不存在: {original_path}"
            
            if not os.path.exists(duplicate_path):
                return False, f"重复文件不存在: {duplicate_path}"
            
            if duplicate_path == original_path:
                return True, "同一路径，跳过"
            
            # 安全检查：防止误删原始文件
            if os.path.samefile(duplicate_path, original_path):
                return True, "已是同一文件（硬链接），无需处理"
            
            # 检查文件系统是否支持符号链接
            if not self._check_fs_supports_symlinks(duplicate_path):
                # 文件系统不支持符号链接，回退到硬链接
                return self._create_hard_link_fallback(duplicate_path, original_path)
            
            temp_path = f"{duplicate_path}.duplicatecleaner-{uuid.uuid4().hex}.tmp"
            success, msg = self.create_symbolic_link(temp_path, original_path)
            if not success:
                return False, f"创建临时符号链接失败: {msg}"
            
            recycle_success, recycle_msg = self.move_to_recycle_bin(duplicate_path)
            if not recycle_success:
                # 回收站失败，清理临时文件并尝试硬链接后备方案
                try:
                    temp_files = glob.glob(f"{duplicate_path}.duplicatecleaner-*.tmp")
                    for tmp in temp_files:
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                except:
                    pass
                return self._create_hard_link_fallback(duplicate_path, original_path)
            
            try:
                os.rename(temp_path, duplicate_path)
                return True, "原文件已移入回收站，原位置已创建符号链接"
            except OSError as e:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                # 重命名失败，尝试硬链接后备方案
                fallback_success, fallback_msg = self._create_hard_link_fallback(duplicate_path, original_path)
                if fallback_success:
                    return True, f"符号链接创建失败，已回退到硬链接: {fallback_msg}"
                return False, f"原文件已移入回收站，但创建原位置符号链接失败: {e}"
        except Exception as e:
            return False, f"替换过程异常: {str(e)}"