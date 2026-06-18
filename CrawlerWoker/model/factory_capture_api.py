from .pattern import PatternFacebook, PatternOther

class FactoryRegexApi:
    def __init__(self):
        self.domain_patterns = {
            "facebook": PatternFacebook()
        }

    def get_pattern(self, url: str):
        for domain, pattern in self.domain_patterns.items():
            if domain in url:
                return pattern
        return  PatternOther()