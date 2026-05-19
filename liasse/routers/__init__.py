"""FastAPI 路由分组。

每个子模块导出一个 `router: APIRouter`，由 web_app.create_app() 用
include_router 挂载。这样 web_app.py 自己只负责装配，每个域的路由
聚集在自己的文件里，方便新 agent 一眼找到对应代码。
"""

from .health import router as health_router
from .models_routes import router as models_router
from .qa import router as qa_router

__all__ = ["health_router", "models_router", "qa_router"]
