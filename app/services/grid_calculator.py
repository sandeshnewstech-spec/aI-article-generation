from app.models.data import WordCountRules

class GridCalculator:
    """Calculates newspaper grid dimensions and word count matrices"""
    
    # Column width mapping (in cm)
    COLUMN_WIDTHS = {
        1: 4.1,
        2: 8.7,
        3: 13.3,
        4: 17.7,
        5: 22.4,
        6: 27.0,
        7: 31.6,
        8: 36.2
    }
    
    # Word count matrix: (column_span, slot_count) -> WordCountRules
    WORD_COUNT_MATRIX = {
        # 1 Column layouts
        (1, 1): {
            "heading": (6, 8),
            "subheading": (8, 12),
            "intro": (30, 45),
            "body": (80, 100),
            "info_box": (30, 50)
        },
        # 2 Column layouts
        (2, 1): {
            "heading": (8, 10),
            "subheading": (10, 14),
            "intro": (40, 60),
            "body": (130, 160),
            "info_box": (40, 60)
        },
        # 3 Column layouts
        (3, 1): {
            "heading": (8, 12),
            "subheading": (10, 14),
            "intro": (70, 85),
            "body": (170, 200),
            "info_box": (50, 70)
        },
        # 4 Column layouts
        (4, 1): {
            "heading": (12, 16),
            "subheading": (15, 20),
            "intro": (70, 85),
            "body": (170, 220),
            "info_box": (60, 80)
        },
        # 5 Column layouts
        (5, 1): {
            "heading": (8, 10),
            "subheading": (16, 20),
            "intro": (70, 90),
            "body": (180, 250),
            "info_box": (60, 90)
        },
        (5, 1, "double"): {
            "heading": (12, 16),
            "subheading": (16, 22),
            "intro": (70, 95),
            "body": (200, 300),
            "info_box": (70, 100)
        }
    }
    
    @staticmethod
    def calculate_column_width(columns: int) -> float:
        """
        Calculate width in cm for given column span
        
        Args:
            columns: Number of columns (1-5)
            
        Returns:
            Width in centimeters
        """
        return GridCalculator.COLUMN_WIDTHS.get(columns, 4.1)
    
    @staticmethod
    def calculate_slot_height(slots: int, page_height: float = 80, 
                             top_margin: float = 4, bottom_margin: float = 3) -> float:
        """
        Calculate height in cm for given slot count
        
        Args:
            slots: Number of vertical slots (1-4)
            page_height: Total page height in cm
            top_margin: Top margin in cm
            bottom_margin: Bottom margin in cm
            
        Returns:
            Height in centimeters
        """
        usable_height = page_height - top_margin - bottom_margin
        return (usable_height / 4) * slots
    
    @staticmethod
    def get_word_count_rules(column_span: int, slot_count: int, 
                            double_line: bool = False) -> WordCountRules:
        """
        Get appropriate word count rules based on layout
        
        Args:
            column_span: Number of columns (1-5)
            slot_count: Number of slots (1-4)
            double_line: Whether to use double-line heading (for 5-column)
            
        Returns:
            WordCountRules object with min/max constraints
        """
        # For 5-column, check if double-line
        if column_span == 5 and double_line:
            key = (5, 1, "double")
        else:
            key = (column_span, slot_count)
        
        # Get rules from matrix, default to 3-column if not found
        # For columns > 5, we'll use 5-column rules but scale body slightly
        if column_span > 5:
            rules = GridCalculator.WORD_COUNT_MATRIX.get((5, 1, "double" if double_line else "single"), GridCalculator.WORD_COUNT_MATRIX[(3, 1)])
            # Scale body max for larger layouts if it's the default 5-col
            if column_span == 8: rules["body"] = (rules["body"][0], rules["body"][1] + 100)
        else:
            rules = GridCalculator.WORD_COUNT_MATRIX.get(key, GridCalculator.WORD_COUNT_MATRIX[(3, 1)])
        
        return WordCountRules(
            heading_min=rules["heading"][0],
            heading_max=rules["heading"][1],
            subheading_min=rules["subheading"][0],
            subheading_max=rules["subheading"][1],
            intro_min=rules["intro"][0],
            intro_max=rules["intro"][1],
            body_min=rules["body"][0],
            body_max=rules["body"][1],
            info_box_min=rules["info_box"][0] if rules["info_box"] else None,
            info_box_max=rules["info_box"][1] if rules["info_box"] else None
        )
    
    @staticmethod
    def calculate_total_area(column_span: int, slot_count: int) -> float:
        """
        Calculate total article area in square cm
        
        Args:
            column_span: Number of columns
            slot_count: Number of slots
            
        Returns:
            Area in square centimeters
        """
        width = GridCalculator.calculate_column_width(column_span)
        height = GridCalculator.calculate_slot_height(slot_count)
        return width * height
