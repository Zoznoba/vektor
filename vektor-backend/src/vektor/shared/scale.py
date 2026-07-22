def convert_scale_1_3_to_1_5(old_score: float) -> float:
    old_min, old_max = 1, 3
    new_min, new_max = 1, 5
    return new_min + (old_score - old_min) * (new_max - new_min) / (old_max - old_min)
