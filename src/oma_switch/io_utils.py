"""
IO 工具模块：文件原子写入、容错 JSON 解析等基础 IO 操作
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# 匹配尾随逗号：逗号后可选空白，然后是 } 或 ]
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _parse_json_tolerant(text: str) -> Dict[str, Any]:
    """解析 JSON 文本，自动修复尾随逗号等常见错误。

    Args:
        text: JSON 文本

    Returns:
        解析后的字典

    Raises:
        json.JSONDecodeError: 修复后仍无法解析
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fixed = _TRAILING_COMMA_RE.sub(r"\1", text)
        return json.loads(fixed)


def _atomic_write_json(
    filepath: Path, data: Dict[str, Any], indent: int = 2, ensure_ascii: bool = False
) -> None:
    """原子性写入 JSON 文件：写入临时文件 → fsync → 原子替换目标文件。"""
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=filepath.parent, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            json.dump(data, tmp_file, indent=indent, ensure_ascii=ensure_ascii)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        # 保留原文件权限
        if filepath.exists():
            shutil.copymode(filepath, tmp_path)
        os.replace(tmp_path, filepath)
    except Exception:
        # 写入失败时清理临时文件，目标文件保持不变
        if tmp_path is not None and tmp_path.exists():
            os.unlink(tmp_path)
        raise
