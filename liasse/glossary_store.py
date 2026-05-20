"""专业词库 CRUD store — outputs/glossaries/<name>.json。

每个词库一个文件,内容是 schemas.Glossary 的 JSON 序列化。
- 文件名走白名单正则避免路径遍历 (../ 等)
- put() 用 tmp + rename 原子写,避免半截文件污染
- delete() 幂等返回 bool

完全离线,无网络/无锁/无依赖 (除 stdlib + pydantic)。
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional

from .schemas import Glossary

# 同 Glossary.name 的 pattern: 中文字符 + 字母数字 + 连字符 + 下划线
_VALID_NAME = re.compile(r"^[\w一-鿿\-]+$")


class GlossaryStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not name or not _VALID_NAME.match(name):
            raise ValueError(f"非法词库名:{name!r}")
        return self.root / f"{name}.json"

    def list_names(self) -> List[str]:
        return sorted(p.stem for p in self.root.glob("*.json") if not p.stem.startswith("."))

    def get(self, name: str) -> Optional[Glossary]:
        p = self._path(name)
        if not p.exists():
            return None
        return Glossary.model_validate_json(p.read_text(encoding="utf-8"))

    def put(self, glossary: Glossary) -> None:
        p = self._path(glossary.name)
        payload = glossary.model_dump_json(indent=2)
        fd, tmp_path = tempfile.mkstemp(prefix=".gloss-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, p)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if not p.exists():
            return False
        p.unlink()
        return True
