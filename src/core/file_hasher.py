import xxhash
import hashlib
import os
from pathlib import Path
from typing import Optional, Callable, List, Tuple, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class FileHash:
    path: str
    xxh64: str
    sha256: Optional[str]
    size: int


class FileHasher:
    def __init__(self, chunk_size: int = 64 * 1024, max_workers: int = None):
        self.chunk_size = chunk_size
        self.max_workers = max_workers or os.cpu_count()

    def compute_xxh64(self, file_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        try:
            hasher = xxhash.xxh64()
            total_size = os.path.getsize(file_path)
            processed = 0
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hasher.update(chunk)
                    processed += len(chunk)
                    if progress_callback:
                        progress_callback(processed, total_size)
            
            return hasher.hexdigest()
        except (OSError, IOError):
            return None

    def compute_sha256(self, file_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        try:
            hasher = hashlib.sha256()
            total_size = os.path.getsize(file_path)
            processed = 0
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hasher.update(chunk)
                    processed += len(chunk)
                    if progress_callback:
                        progress_callback(processed, total_size)
            
            return hasher.hexdigest()
        except (OSError, IOError):
            return None

    def compute_xxh64_batch(self, file_paths: List[str], progress_callback: Optional[Callable[[int, int, str], None]] = None) -> Dict[str, Optional[str]]:
        """并行计算多个文件的 xxh64"""
        results = {}
        
        def compute_single(path: str) -> Tuple[str, Optional[str]]:
            return path, self.compute_xxh64(path)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {executor.submit(compute_single, path): path for path in file_paths}
            completed = 0
            total = len(file_paths)
            for future in as_completed(future_to_path):
                path, result = future.result()
                results[path] = result
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, path)
        
        return results

    def compute_sha256_batch(self, file_paths: List[str], progress_callback: Optional[Callable[[int, int, str], None]] = None) -> Dict[str, Optional[str]]:
        """并行计算多个文件的 sha256（仅对 xxh64 相同的文件）"""
        results = {}
        
        def compute_single(path: str) -> Tuple[str, Optional[str]]:
            return path, self.compute_sha256(path)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {executor.submit(compute_single, path): path for path in file_paths}
            completed = 0
            total = len(file_paths)
            for future in as_completed(future_to_path):
                path, result = future.result()
                results[path] = result
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, path)
        
        return results

    def compute_hashes(self, file_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[FileHash]:
        """兼容旧接口：计算单个文件的完整哈希"""
        try:
            size = os.path.getsize(file_path)
            xxh64 = self.compute_xxh64(file_path, progress_callback)
            if xxh64 is None:
                return None
            sha256 = self.compute_sha256(file_path, progress_callback)
            if sha256 is None:
                return None
            
            return FileHash(
                path=file_path,
                xxh64=xxh64,
                sha256=sha256,
                size=size
            )
        except (OSError, IOError):
            return None

    def quick_compare(self, file1: str, file2: str) -> bool:
        try:
            if os.path.getsize(file1) != os.path.getsize(file2):
                return False
            
            h1 = self.compute_xxh64(file1)
            h2 = self.compute_xxh64(file2)
            return h1 == h2 and h1 is not None
        except (OSError, IOError):
            return False