class DevMatcher:
    def __init__(self, weights=None):
        self.weights = weights or {"languages": 0.6, "experience": 0.2, "culture": 0.2}

    def calculate_compatibility(self, dev1, dev2):
        common_langs = set(dev1["stack"]) & set(dev2["stack"])
        if not dev1["stack"]:
            return 0.0

        lang_score = len(common_langs) / len(dev1["stack"])
        exp_diff = abs(dev1["years"] - dev2["years"])
        exp_score = 1 / (1 + exp_diff)

        culture_match = 0.0
        if dev1.get("prefers_tabs") == dev2.get("prefers_tabs"):
            culture_match += 0.5
        if dev1.get("dark_mode") == dev2.get("dark_mode"):
            culture_match += 0.5

        total = (
            lang_score * self.weights["languages"]
            + exp_score * self.weights["experience"]
            + culture_match * self.weights["culture"]
        )
        return round(total * 100, 2)

