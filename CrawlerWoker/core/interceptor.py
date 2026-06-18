from playwright.async_api import Response
from model.factory_capture_api import FactoryRegexApi


class Interceptor:
    def __init__(self, factory: FactoryRegexApi, domain_name: str):
        self.factory = factory
        self.storage_data = []
        self.domain_name = domain_name

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

        content_type = response.headers.get("content-type", "")

        if (
            "json" not in content_type
            and "text" not in content_type
            and "graphql" not in content_type
        ):
            return

        try:
            data = await response.text()
        except Exception:
            data = None

        self.storage_data.append(
            {
                "url": url,
                "method": request.method,
                "status": response.status,
                "resource_type": request.resource_type,
                "content_type": content_type,
                "post_data": request.post_data,
                "data": data if data else None,
            }
        )
