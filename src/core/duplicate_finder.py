from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple
from pathlib import Path
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .everything_search import EverythingSearch, FileInfo
from .file_hasher import FileHasher, FileHash
from .ntfs_linker import NTFSLinker, LinkType


@dataclass
class DuplicateGroup:
    size: int
    files: List[FileInfo] = field(default_factory=list)
    hashes: Dict[str, FileHash] = field(default_factory=dict)
    confirmed_duplicates: List[FileInfo] = field(default_factory=list)
    keep_file: Optional[FileInfo] = None


@dataclass
class ScanResult:
    groups: List[DuplicateGroup] = field(default_factory=list)
    total_files_scanned: int = 0
    total_duplicate_groups: int = 0
    total_duplicate_files: int = 0
    total_wasted_space: int = 0


class DuplicateFinder:
    def __init__(self, es_path: str = "es.exe", max_workers: int = None):
        self.everything = EverythingSearch(es_path)
        self.hasher = FileHasher(max_workers=max_workers)
        self.linker = NTFSLinker()
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None
        self._cancel_flag = False

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        self._progress_callback = callback

    def cancel(self):
        self._cancel_flag = True

    def _update_progress(self, current: int, total: int, message: str):
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def scan_directory(self, directory: str, min_size: int = 1) -> ScanResult:
        return self.scan_directories([directory], min_size)

    def scan_directories(self, directories: List[str], min_size: int = 1) -> ScanResult:
        if not self.everything.is_available():
            raise RuntimeError(f"Everything (es.exe) 不可用: {self.everything.get_status_text()}\n请在设置中配置正确的 es.exe 路径")
        
        self._cancel_flag = False
        result = ScanResult()
        
        self._update_progress(0, 100, f"正在使用 Everything 搜索 {len(directories)} 个目录...")
        size_groups = self.everything.find_duplicates_by_size_multiple(
            directories, min_size, 
            lambda c, t, m: self._update_progress(c, t, m)
        )
        
        if self._cancel_flag:
            return result
        
        result.total_files_scanned = sum(len(files) for files in size_groups.values())
        
        self._update_progress(10, 100, f"发现 {len(size_groups)} 组相同大小文件，正在计算指纹...")
        
        group_list = []
        size_group_list = []
        for size, files in size_groups.items():
            if self._cancel_flag:
                break
            
            group = DuplicateGroup(size=size, files=files)
            size_group_list.append(group)
        
        for i, group in enumerate(size_group_list):
            if self._cancel_flag:
                break
            
            progress = 10 + int(80 * i / max(len(size_group_list), 1))
            self._update_progress(progress, 100, f"正在比对组 {i+1}/{len(size_group_list)} ({len(group.files)} 个文件)...")
            
            self._compute_hashes_for_group(group)
            group_list.extend(self._identify_duplicates_in_group(group))
        
        for group in group_list:
            if group.confirmed_duplicates:
                result.total_duplicate_files += len(group.confirmed_duplicates)
                result.total_wasted_space += group.size * len(group.confirmed_duplicates)
        
        result.groups = [group for group in group_list if group.confirmed_duplicates]
        result.total_duplicate_groups = len(result.groups)
        
        if not self._cancel_flag:
            self._update_progress(100, 100, "扫描完成")
        
        return result

    def _compute_hashes_for_group(self, group: DuplicateGroup):
        """两阶段哈希：先并行算 xxh64，仅对相同 xxh64 的文件再算 sha256"""
        file_paths = [f.path for f in group.files]
        
        # 第一阶段：并行计算 xxh64
        def xxh64_progress(completed, total, path):
            if self._progress_callback:
                self._progress_callback(0, 0, f"计算 xxh64: {completed}/{total} - {os.path.basename(path)}")
        
        xxh64_results = self.hasher.compute_xxh64_batch(
            file_paths, 
            xxh64_progress if self._progress_callback else None
        )
        
        if self._cancel_flag:
            return
        
        # 按 xxh64 分组
        xxh64_groups: Dict[str, List[str]] = defaultdict(list)
        for path, xxh64 in xxh64_results.items():
            if xxh64:
                xxh64_groups[xxh64].append(path)
        
        # 第二阶段：仅对 xxh64 相同的文件组并行计算 sha256
        sha256_results = {}
        for xxh64, paths in xxh64_groups.items():
            if self._cancel_flag:
                break
            if len(paths) < 2:
                continue
            
            def sha256_progress(completed, total, path):
                if self._progress_callback:
                    self._progress_callback(0, 0, f"计算 sha256: {completed}/{len(paths)} - {os.path.basename(path)}")
            
            batch_results = self.hasher.compute_sha256_batch(
                paths,
                sha256_progress if self._progress_callback else None
            )
            sha256_results.update(batch_results)
        
        # 组装结果
        for file_info in group.files:
            xxh64 = xxh64_results.get(file_info.path)
            if xxh64 is None:
                continue
            sha256 = sha256_results.get(file_info.path)
            group.hashes[file_info.path] = FileHash(
                path=file_info.path,
                xxh64=xxh64,
                sha256=sha256,
                size=file_info.size
            )

    def _identify_duplicates_in_group(self, group: DuplicateGroup) -> List[DuplicateGroup]:
        hash_groups: Dict[str, List[FileInfo]] = defaultdict(list)
        
        for file_info in group.files:
            if file_info.path in group.hashes:
                hash_key = group.hashes[file_info.path].xxh64
                hash_groups[hash_key].append(file_info)
        
        duplicate_groups: List[DuplicateGroup] = []
        for files in hash_groups.values():
            if len(files) < 2:
                continue
            
# 选择保留文件：所有文件中文件名评分最好的一个
            files.sort(key=lambda f: (self._filename_score(f.name), f.modified_time))
            keep_file = files[0]
            keep_hash = group.hashes.get(keep_file.path)
            
            # 其他所有文件都是待删除的重复文件
            # 但排除：如果是软链接且其内容哈希与保留文件相同，则不视为重复
            confirmed_duplicates = []
            for f in files:
                if f.path == keep_file.path:
                    continue
                # 如果是软链接且其内容哈希与保留文件相同，则不视为重复
                if os.path.islink(f.path):
                    f_hash = group.hashes.get(f.path)
                    if f_hash and keep_hash and f_hash.xxh64 == keep_hash.xxh64:
                        # 软链接指向相同内容，不视为重复
                        continue
                confirmed_duplicates.append(f)
            
            # 创建重复组
            duplicate_groups.append(
                DuplicateGroup(
                    size=group.size,
                    files=files,
                    hashes={path: group.hashes[path] for path in [f.path for f in files] if path in group.hashes},
                    confirmed_duplicates=confirmed_duplicates,
                    keep_file=keep_file,
                )
            )
        
        return duplicate_groups

    def _get_file_indices_batch(self, file_paths: List[str]) -> Dict[str, Optional[tuple]]:
        """并行获取多个文件的索引"""
        results = {}
        
        def get_single(path: str) -> Tuple[str, Optional[tuple]]:
            return path, self.linker.get_file_index(path)
        
        with ThreadPoolExecutor(max_workers=min(len(file_paths), os.cpu_count() or 4)) as executor:
            future_to_path = {executor.submit(get_single, path): path for path in file_paths}
            for future in as_completed(future_to_path):
                path, identity = future.result()
                results[path] = identity
        
        return results

    def _filename_score(self, filename: str) -> tuple:
        """
        Score filename for keep-file preference.
        Lower score = better candidate to keep.
        Returns (has_parens, max_number, number_count, length)
        
        Examples:
          'file.rar'           -> (False, 0, 0, 7)  best
          'file(1).rar'        -> (True, 1, 1, 11)
          'file(2).rar'        -> (True, 2, 1, 11)
          'file(1)(1).rar'     -> (True, 1, 2, 14)   fewer numbers better
          'file(10).rar'       -> (True, 10, 1, 12)
          'file-副本.rar'      -> (False, 0, 0, 10)  shorter than 'file(1).rar'
        """
        import re
        matches = re.findall(r'\((\d+)\)', filename)
        has_parens = bool(matches)
        if not matches:
            numbers = []
        else:
            numbers = [int(m) for m in matches]
        
        # Add filename length as a tiebreaker (shorter is better)
        length = len(filename)
        
        if not matches:
            return (False, 0, 0, len(filename))
        return (True, min(matches), len(matches), len(filename))
    
    def apply_action(self, group: DuplicateGroup, action: str, link_type: LinkType = LinkType.HARD_LINK) -> List[Tuple[str, bool, str]]:
        results = []
        
        if action == "delete" and group.keep_file:
            for dup_file in group.confirmed_duplicates:
                if self._cancel_flag:
                    break
                
                # 安全检查：跳过保留文件
                if os.path.abspath(dup_file.path) == os.path.abspath(group.keep_file.path):
                    continue
                
                success, msg = self.linker.replace_with_symlink(dup_file.path, group.keep_file.path)
                results.append((dup_file.path, success, msg))
        
        elif action == "hardlink" and group.keep_file:
            for dup_file in group.confirmed_duplicates:
                if self._cancel_flag:
                    break
                
                success, msg = self.linker.create_hard_link(dup_file.path + ".hlink", group.keep_file.path)
                results.append((dup_file.path, success, msg))
        
        elif action == "symlink" and group.keep_file:
            for dup_file in group.confirmed_duplicates:
                if self._cancel_flag:
                    break
                
                success, msg = self.linker.create_symbolic_link(dup_file.path + ".symlink", group.keep_file.path)
                results.append((dup_file.path, success, msg))
        
        return results