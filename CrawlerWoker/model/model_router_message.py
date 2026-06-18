import os
from dotenv import load_dotenv

load_dotenv()

TOPIC_TASK_CRAWL = os.getenv("TOPIC_TASK_CRAWL")


class SearchContentKeyWord:
    def __init__(self, message: dict):
        self.message = message
        if self.message["content_type"] == "post":
            self.crawler = self.SearchContentPost(message)
        elif self.message["content_type"] == "video":
            self.crawler = self.SearchContentVideo(message)
        else:
            raise ValueError("Invalid content type")

    class SearchContentPost:
        def __init__(self, message: dict):
            self.message = message

        def crawl_search_content_post(self):
            pass

    class SearchContentVideo:
        def __init__(self, message: dict):
            self.message = message

        def crawl_search_content_video(self):
            pass


class SearchContentEntity:
    def __init__(self, message: dict):
        self.message = message

    def crawl_search_content_entity(self):
        pass


factory_router_crawler = {
    "search_content_keyword": SearchContentKeyWord,
    "search_content_entity": SearchContentEntity,
}
