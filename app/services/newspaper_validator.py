from typing import List, Tuple, Dict
from app.models.data import NewspaperOutput, NewspaperConfig, WordCountRules
import re

class NewspaperValidator:
    """Validates newspaper article output against configuration rules"""
    
    @staticmethod
    def count_words(text: str) -> int:
        """Count words in text"""
        return len(text.strip().split())
    
    @staticmethod
    def validate_word_counts(output: NewspaperOutput, 
                            rules: WordCountRules) -> Tuple[bool, List[str]]:
        """
        Validate all sections meet word count requirements
        
        Args:
            output: Generated newspaper output
            rules: Word count rules to validate against
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Validate heading
        heading_count = NewspaperValidator.count_words(output.headline)
        if not (rules.heading_min <= heading_count <= rules.heading_max):
            errors.append(
                f"Heading word count {heading_count} not in range "
                f"{rules.heading_min}-{rules.heading_max}"
            )
        
        # Validate subheading if present
        if output.subheading:
            sub_count = NewspaperValidator.count_words(output.subheading)
            if not (rules.subheading_min <= sub_count <= rules.subheading_max):
                errors.append(
                    f"Subheading word count {sub_count} not in range "
                    f"{rules.subheading_min}-{rules.subheading_max}"
                )
        
        # Validate intro
        intro_count = NewspaperValidator.count_words(output.intro)
        if not (rules.intro_min <= intro_count <= rules.intro_max):
            errors.append(
                f"Intro word count {intro_count} not in range "
                f"{rules.intro_min}-{rules.intro_max}"
            )
        
        # Validate body
        body_count = NewspaperValidator.count_words(output.body)
        if not (rules.body_min <= body_count <= rules.body_max):
            errors.append(
                f"Body word count {body_count} not in range "
                f"{rules.body_min}-{rules.body_max}"
            )
        
        # Validate info box if present and required
        if output.info_box and rules.info_box_min and rules.info_box_max:
            info_count = NewspaperValidator.count_words(output.info_box)
            if not (rules.info_box_min <= info_count <= rules.info_box_max):
                errors.append(
                    f"Info box word count {info_count} not in range "
                    f"{rules.info_box_min}-{rules.info_box_max}"
                )
        
        return len(errors) == 0, errors
    
    @staticmethod
    def check_repetition(text: str, threshold: int = 3) -> Tuple[bool, List[str]]:
        """
        Check for excessive word/phrase repetition
        
        Args:
            text: Text to check
            threshold: Maximum allowed repetitions
            
        Returns:
            Tuple of (is_valid, list of repeated words)
        """
        # Split into words and count occurrences
        words = text.lower().split()
        word_counts = {}
        
        for word in words:
            # Skip very short words and common words
            if len(word) <= 2 or word in ['અને', 'છે', 'થી', 'માં', 'ને', 'તે']:
                continue
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # Find words repeated more than threshold
        repeated = [word for word, count in word_counts.items() if count > threshold]
        
        return len(repeated) == 0, repeated
    
    @staticmethod
    def verify_sources(content: str, allowed_sources: List[str]) -> Tuple[bool, str]:
        """
        Verify content only uses allowed sources
        
        This is a basic check - looks for source mentions in content
        
        Args:
            content: Article content
            allowed_sources: List of allowed source domains
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not allowed_sources:
            return True, "No source restrictions"
        
        # This is a simplified check
        # In production, you'd track which sources were actually used during scraping
        content_lower = content.lower()
        
        # Check if any disallowed sources are mentioned
        common_sources = [
            "wikipedia", "google", "facebook", "twitter", "instagram",
            "whatsapp", "social media"
        ]
        
        for source in common_sources:
            if source in content_lower and source not in [s.lower() for s in allowed_sources]:
                return False, f"Unauthorized source mentioned: {source}"
        
        return True, "Source verification passed"
    
    @staticmethod
    def validate_editorial_filters(output: NewspaperOutput,
                                   config: NewspaperConfig) -> Tuple[bool, List[str]]:
        """
        Validate editorial style filters
        
        Args:
            output: Generated output
            config: Configuration with editorial filters
            
        Returns:
            Tuple of (is_valid, list of warnings)
        """
        warnings = []
        filters = config.editorial_filters
        
        # Check for active voice if required
        if filters.active_voice:
            passive_indicators = ["કરાયું", "આપવામાં આવ્યું", "લેવામાં આવ્યું"]
            full_text = f"{output.headline} {output.intro} {output.body}"
            if any(indicator in full_text for indicator in passive_indicators):
                warnings.append("Passive voice detected - prefer active voice")
        
        # Check for number highlighting if required
        if filters.highlight_numbers:
            # This would be handled in the AI prompt
            # Just a placeholder check here
            pass
        
        return len(warnings) == 0, warnings
    
    @staticmethod
    def comprehensive_validation(output: NewspaperOutput,
                                config: NewspaperConfig) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Run all validations
        
        Args:
            output: Generated newspaper output
            config: Configuration to validate against
            
        Returns:
            Tuple of (is_valid, dict of validation results by category)
        """
        results = {
            "word_counts": [],
            "repetition": [],
            "sources": [],
            "editorial": [],
            "headline": []
        }
        
        # Word count validation
        wc_valid, wc_errors = NewspaperValidator.validate_word_counts(
            output, config.word_count_rules
        )
        results["word_counts"] = wc_errors
        
        # Repetition check
        full_text = f"{output.headline} {output.intro} {output.body}"
        rep_valid, repeated = NewspaperValidator.check_repetition(full_text)
        if not rep_valid:
            results["repetition"] = [f"Repeated words: {', '.join(repeated[:5])}"]
        
        # Source verification
        src_valid, src_msg = NewspaperValidator.verify_sources(
            full_text, config.allowed_sources
        )
        if not src_valid:
            results["sources"] = [src_msg]
        
        # Editorial filters
        ed_valid, ed_warnings = NewspaperValidator.validate_editorial_filters(
            output, config
        )
        results["editorial"] = ed_warnings
        
        # Overall validity
        is_valid = all([
            wc_valid,
            rep_valid,
            src_valid,
            len(results["headline"]) == 0
        ])
        
        return is_valid, results
