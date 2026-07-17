"""
Text Accuracy Metrics для RL rewards.
"""

from typing import List, Tuple
import re


class TextAccuracyMetrics:
    """Metrics for text rendering accuracy."""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase, remove extra whitespace
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def word_accuracy(self, target: str, recognized: str) -> float:
        """
        Word-level accuracy.
        
        Returns fraction of target words found in recognized text.
        """
        target = self.normalize_text(target)
        recognized = self.normalize_text(recognized)
        
        if not target:
            return 1.0 if not recognized else 0.0
            
        target_words = set(target.split())
        recognized_words = set(recognized.split())
        
        if not target_words:
            return 1.0
            
        matches = len(target_words & recognized_words)
        return matches / len(target_words)
    
    def char_accuracy(self, target: str, recognized: str) -> float:
        """
        Character-level accuracy.
        """
        target = self.normalize_text(target).replace(" ", "")
        recognized = self.normalize_text(recognized).replace(" ", "")
        
        if not target:
            return 1.0 if not recognized else 0.0
            
        target_chars = set(target)
        recognized_chars = set(recognized)
        
        matches = len(target_chars & recognized_chars)
        return matches / len(target_chars)
    
    def normalized_edit_distance(self, target: str, recognized: str) -> float:
        """
        Normalized Edit Distance (NED).
        
        Lower is better. 0 = perfect match.
        Returns 1 - NED for use as reward (higher is better).
        """
        target = self.normalize_text(target)
        recognized = self.normalize_text(recognized)
        
        if not target:
            return 1.0 if not recognized else 0.0
            
        # Levenshtein distance
        m, n = len(target), len(recognized)
        
        if m == 0:
            return 0.0 if n == 0 else 0.0
            
        # DP table
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
            
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if target[i-1] == recognized[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
                    
        ned = dp[m][n] / max(m, n)
        return 1.0 - ned  # Convert to reward (higher is better)
    
    def compute_all(self, target: str, recognized: str) -> dict:
        """Compute all metrics."""
        return {
            "word_accuracy": self.word_accuracy(target, recognized),
            "char_accuracy": self.char_accuracy(target, recognized),
            "ned_reward": self.normalized_edit_distance(target, recognized),
        }
