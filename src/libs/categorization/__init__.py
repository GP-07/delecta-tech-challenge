"""Menu item categorization: assigns each dish of a menu to a category of the food taxonomy (food_categories.xlsx).

Pure library, no Django: rules (keywords of dish names and menu sections) first, then text embeddings for what the
rules do not cover.
"""
