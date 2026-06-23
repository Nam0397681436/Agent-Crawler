import re


class PatternFacebook:
    # 1. Các API rác, theo dõi hành vi -> BỎ QUA NGAY
    url_skip_facebook = [
        r"facebook\.com/ajax/device/",
        r"facebook\.com/ajax/logger/",
        r"facebook\.com/ajax/ua/",
        r"facebook\.com/async/",
        r"facebook\.com/logging/",
        r"facebook\.com/tr/",
        # Bỏ qua tất cả các file ảnh/âm thanh/video không phải là jpg/jpeg
        r"\.(png|webp|gif|svg|ico|bmp|tiff|avif|mp3|mp4|wav|ogg|webm|m4a|aac)(?:$|\?)",
    ]

    url_pattern_extract = [
        r"facebook\.com",       # Giữ lại facebook.com để không làm hỏng các API lấy data (như bulk-route-definitions)
        r"\.jpe?g(?:$|\?)",     # Bắt các file .jpg hoặc .jpeg (thường từ fbcdn.net)
    ]

    def __init__(self):

        self.skip_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.url_skip_facebook
        ]
        self.extract_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.url_pattern_extract
        ]


class PatternOther:
    def __init__(self):
        # 1. Danh sách Đen Toàn Cầu: Bỏ qua tất cả API tải tài nguyên tĩnh hoặc thu thập dữ liệu rác
        self.global_skip_patterns = [
            # Tệp tĩnh: Ảnh, Biểu tượng, Đồ họa
            r"\.(png|jpg|jpeg|gif|webp|svg|ico|bmp|tiff|avif)$",
            # Phông chữ & Định dạng hiển thị
            r"\.(woff|woff2|ttf|eot|otf)$",
            # Tệp cấu trúc giao diện tĩnh (Nếu bạn chỉ muốn lấy dữ liệu JSON API, hãy bỏ qua .css/.js tĩnh)
            r"\.(css|less|scss)$",
            # Các thư viện tracking, quảng cáo, phân tích hành vi phổ biến trên mọi website
            r"(google-analytics|analytics\.js|gtag|google-analytics\.com)",
            r"(facebook\.com/tr|connect\.facebook\.net|fbcdn\.net)",  # Pixel của FB cài trên web khác
            r"(mixpanel|hotjar|amplitude|segment\.io|clarity\.ms)",
            r"(doubleclick|adnxs|adsystem|adskeeper|popads|histats)",
            # Từ khóa API đặc trưng của Log hệ thống / Telemetry / Sửa lỗi
            r"/(logger|logging|telemetry|metrics|beacon|stats|ping|pong|heartbeat|collect|track|report)/",
            r"/(error-report|sentry|bugsnag|rollbar|crashlytics)/",
        ]

        self.skip_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.global_skip_patterns
        ]
        self.extract_compiled = []
