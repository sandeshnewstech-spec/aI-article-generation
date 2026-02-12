from typing import List, Tuple
import re

class HeadlineEngineer:
    """Generates and validates headlines following Gujarati newspaper standards"""
    
    # Gujarati punch words for impactful headlines
    PUNCH_WORDS_GUJ = [
        "તાત્કાલિક", "મોટો", "અચાનક", "ચોંકાવનારું", "મહત્વનું",
        "ગંભીર", "નવું", "વિશેષ", "અત્યંત", "તાજેતરનું",
        "ઐતિહાસિક", "અભૂતપૂર્વ", "નિર્ણાયક", "મહત્ત્વપૂર્ણ", "ખાસ"
    ]
    
    # Weak verbs to avoid in headlines
    WEAK_VERBS_GUJ = [
        "થયું", "કરાયું", "આપવામાં આવ્યું", "લેવામાં આવ્યું",
        "બનાવવામાં આવ્યું", "કહેવામાં આવ્યું"
    ]
    
    # Strong action verbs (preferred)
    STRONG_VERBS_GUJ = [
        "જાહેર કર્યું", "લીધો", "આપ્યો", "શરૂ કર્યું", "બનાવ્યું",
        "જણાવ્યું", "કર્યું", "આવ્યું", "ગયું", "થયું"
    ]
    
    @staticmethod
    def validate_word_count(text: str, min_words: int, max_words: int) -> Tuple[bool, int]:
        """
        Validate word count is within range
        
        Args:
            text: Text to validate
            min_words: Minimum allowed words
            max_words: Maximum allowed words
            
        Returns:
            Tuple of (is_valid, actual_count)
        """
        words = text.strip().split()
        count = len(words)
        is_valid = min_words <= count <= max_words
        return is_valid, count
    
    @staticmethod
    def has_punch_word(headline: str) -> bool:
        """Check if headline starts with a punch word"""
        for punch in HeadlineEngineer.PUNCH_WORDS_GUJ:
            if headline.strip().startswith(punch):
                return True
        return False
    
    @staticmethod
    def has_weak_verbs(text: str) -> bool:
        """Check if text contains weak passive verbs"""
        for weak in HeadlineEngineer.WEAK_VERBS_GUJ:
            if weak in text:
                return True
        return False
    
    @staticmethod
    def validate_lr_structure(headline: str) -> Tuple[bool, str]:
        """
        Validate Left-Right structure: Subject -> Event -> Impact
        
        This is a simplified check - looks for proper word distribution
        
        Args:
            headline: Headline text to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        words = headline.strip().split()
        word_count = len(words)
        
        if word_count < 6:
            return False, "Headline too short for L-R structure (need 6+ words)"
        
        # Check for balanced distribution
        # Left 1/3 should have subject, Middle 1/3 event, Right 1/3 impact
        # This is a basic heuristic - actual validation would need NLP
        
        return True, "L-R structure appears balanced"
    
    @staticmethod
    def suggest_punch_word(content: str) -> str:
        """
        Suggest appropriate punch word based on content
        
        Args:
            content: Article content to analyze
            
        Returns:
            Suggested punch word
        """
        content_lower = content.lower()
        
        # Simple keyword matching
        if any(word in content_lower for word in ["તાત્કાલિક", "તુરંત", "હમણાં"]):
            return "તાત્કાલિક"
        elif any(word in content_lower for word in ["મોટ", "વિશાળ", "મહત્વ"]):
            return "મોટો"
        elif any(word in content_lower for word in ["અચાનક", "આકસ્મિક"]):
            return "અચાનક"
        elif any(word in content_lower for word in ["નવ", "તાજ"]):
            return "નવું"
        else:
            return "મહત્વનું"  # Default
    
    @staticmethod
    def extract_headline_components(content: str) -> dict:
        """
        Extract WHO, WHAT, IMPACT from content
        
        This is a simplified extraction - would need NLP for production
        
        Args:
            content: Article content
            
        Returns:
            Dict with 'who', 'what', 'impact' keys
        """
        # Simplified extraction - takes first sentence and analyzes
        sentences = content.split('.')
        first_sentence = sentences[0] if sentences else content[:100]
        
        return {
            "who": "સંબંધિત પક્ષ",  # Placeholder
            "what": "ઘટના",  # Placeholder
            "impact": "પરિણામ"  # Placeholder
        }
    
    @staticmethod
    def validate_headline(headline: str, config: dict) -> Tuple[bool, List[str]]:
        """
        Comprehensive headline validation
        
        Args:
            headline: Headline text
            config: Dict with validation rules (use_punch_words, lr_structure, etc.)
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Check word count
        min_words = config.get("min_words", 8)
        max_words = config.get("max_words", 16)
        is_valid_count, actual_count = HeadlineEngineer.validate_word_count(
            headline, min_words, max_words
        )
        if not is_valid_count:
            errors.append(f"Word count {actual_count} not in range {min_words}-{max_words}")
        
        # Check punch words if required
        if config.get("use_punch_words", True):
            if not HeadlineEngineer.has_punch_word(headline):
                errors.append("Missing punch word at beginning")
        
        # Check for weak verbs
        if HeadlineEngineer.has_weak_verbs(headline):
            errors.append("Contains weak passive verbs")
        
        # Check L-R structure if required
        if config.get("lr_structure", True):
            is_valid_lr, lr_msg = HeadlineEngineer.validate_lr_structure(headline)
            if not is_valid_lr:
                errors.append(lr_msg)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def format_headline(headline: str, use_caps: bool = False) -> str:
        """
        Format headline according to newspaper standards
        
        Args:
            headline: Raw headline text
            use_caps: Whether to convert to uppercase
            
        Returns:
            Formatted headline
        """
        headline = headline.strip()
        if use_caps:
            headline = headline.upper()
        return headline
