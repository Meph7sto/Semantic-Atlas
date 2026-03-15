import json
import os
import sys
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ["SKIP_DB_INIT"] = "1"

from backend_business.config import settings
from backend_business.services.db_service import DBService


def _wait_for_db(dsn: str, attempts: int = 10, delay: float = 2.0) -> DBService:
    last_error = None
    for i in range(1, attempts + 1):
        try:
            return DBService(dsn=dsn)
        except Exception as exc:  # pragma: no cover - lightweight retry for startup
            last_error = exc
            print(f"[test] database not ready, retry {i}/{attempts}...")
            time.sleep(delay)
    raise last_error


def main() -> int:
    print("[test] using dsn:", settings.POSTGRES_DSN)
    db = _wait_for_db(settings.POSTGRES_DSN)

    rel_id = db.save_relation(
        high_level_requirement="系统应提供用户登录功能。",
        low_level_requirement="实现用户名密码校验与会话管理。",
        output={"summary": "关系存在", "score": 0.87},
        title="测试-单对",
    )
    print("[test] inserted relation id:", rel_id)

    batch_id = db.save_batch(
        high_level_requirements=["系统应提供登录功能", "系统应记录审计日志"],
        low_level_requirements=["实现用户认证", "记录用户操作"],
        output={"summary": "批量完成", "pairs": 2},
        title="测试-批量",
    )
    print("[test] inserted batch id:", batch_id)

    listing = db.list_requirements(page=1, per_page=5)
    print("[test] list_requirements:", json.dumps(listing, ensure_ascii=False))

    detail = db.get_requirement_detail(rel_id)
    print("[test] get_requirement_detail:", json.dumps(detail, ensure_ascii=False))

    stats = db.statistics()
    print("[test] statistics:", json.dumps(stats, ensure_ascii=False))

    deleted = db.delete_requirement(rel_id)
    print("[test] delete_requirement:", deleted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
