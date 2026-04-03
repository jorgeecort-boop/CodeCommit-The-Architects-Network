class DevMatcher:
    def __init__(self, weights=None):
        self.weights = weights or {"languages": 0.4, "experience": 0.15, "culture": 0.1, "karma": 0.15, "streak": 0.1, "complementary": 0.1}

    def calculate_compatibility(self, dev1, dev2):
        if not dev1.get("stack"):
            return 0.0

        lang_set1 = set(dev1["stack"])
        lang_set2 = set(dev2["stack"])
        common_langs = lang_set1 & lang_set2
        
        lang_score = len(common_langs) / len(lang_set1)
        
        complementaria = lang_set1 - lang_set2
        if complementaria and lang_set2:
            comp_score = 0.3
        else:
            comp_score = 0.0
        
        exp_diff = abs(dev1.get("years", 0) - dev2.get("years", 0))
        exp_score = 1 / (1 + exp_diff)
        
        culture_match = 0.0
        if dev1.get("prefers_tabs") == dev2.get("prefers_tabs"):
            culture_match += 0.5
        if dev1.get("dark_mode") == dev2.get("dark_mode"):
            culture_match += 0.5
        
        karma1 = dev1.get("karma_score", 0) or 0
        karma2 = dev2.get("karma_score", 0) or 0
        avg_karma = (karma1 + karma2) / 2
        karma_score = min(avg_karma / 100, 1.0)
        
        streak1 = dev1.get("current_streak", 0) or 0
        streak2 = dev2.get("current_streak", 0) or 0
        avg_streak = (streak1 + streak2) / 2
        streak_score = min(avg_streak / 7, 1.0)
        
        total = (
            lang_score * self.weights["languages"]
            + comp_score * self.weights["complementary"]
            + exp_score * self.weights["experience"]
            + culture_match * self.weights["culture"]
            + karma_score * self.weights["karma"]
            + streak_score * self.weights["streak"]
        )
        return round(total * 100, 2)

    def suggest_matches(self, user, candidates, limit=10):
        scored = []
        for candidate in candidates:
            if candidate.get("id") == user.get("id"):
                continue
            score = self.calculate_compatibility(user, candidate)
            candidate_with_score = {**candidate, "match_score": score}
            scored.append(candidate_with_score)
        
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        return scored[:limit]