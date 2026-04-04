"""Run the control plane: python -m services.control_plane"""

import uvicorn

from packages.shared.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "services.control_plane.app:app",
        host=settings.control_plane_host,
        port=settings.control_plane_port,
        reload=True,
    )
