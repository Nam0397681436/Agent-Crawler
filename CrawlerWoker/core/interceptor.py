import os
import uuid
from playwright.async_api import Response
from model.factory_capture_api import FactoryRegexApi


class Interceptor:
    def __init__(self, factory: FactoryRegexApi, domain_name: str):
        self.factory = factory
        self.storage_data = []
        self.bulk_route_data = []
        self.domain_name = domain_name
        self.media_dir = os.path.join(os.getcwd(), "media")
        os.makedirs(self.media_dir, exist_ok=True)

    async def capture_network(self, response: Response):
        url = response.url
        request = response.request
        pattern_manager = self.factory.get_pattern(self.domain_name)

        if pattern_manager:
            for regex in pattern_manager.skip_compiled:
                if regex.search(url):
                    return

            should_capture = False

            if pattern_manager.extract_compiled:
                for regex in pattern_manager.extract_compiled:
                    if regex.search(url):
                        should_capture = True
                        break
            else:
                should_capture = True

            if not should_capture:
                return

        # Check for bulk-route-definitions specifically to push to a separate queue
        if "bulk-route-definitions/" in url:
            try:
                data = await response.text()
                self.bulk_route_data.append(
                    {
                        "url": url,
                        "method": request.method,
                        "status": response.status,
                        "data": data,
                    }
                )
            except Exception:
                pass
            return  # Push to separate queue and exit

        content_type = response.headers.get("content-type", "")

        is_media = "image" in content_type or "video" in content_type
        is_text = "json" in content_type or "text" in content_type or "graphql" in content_type

        if not is_media and not is_text:
            return

        data = None
        media_path = None

        if is_media:
            try:
                # Lấy binary body của ảnh/video
                body = await response.body()
                if body:
                    # Tạo tên file random để tránh trùng lặp
                    ext = content_type.split("/")[-1].split(";")[0]
                    if ext == "jpeg":
                        ext = "jpg"
                    
                    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
                    local_path = os.path.join(self.media_dir, filename)
                    
                    with open(local_path, "wb") as f:
                        f.write(body)
                    
                    media_path = local_path
            except Exception:
                pass
        else:
            try:
                data = await response.text()
            except Exception:
                pass

        self.storage_data.append(
            {
                "url": url,
                "method": request.method,
                "status": response.status,
                "resource_type": request.resource_type,
                "content_type": content_type,
                "post_data": request.post_data,
                "data": data,
                "media_path": media_path,
            }
        )
