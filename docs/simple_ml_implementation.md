# Simple ML Implementation for Ever Learning Feature

## Overview

This document outlines the simplest possible ML implementation for the ever learning feature that will run efficiently on CPU without requiring a GPU.

## CPU-Friendly Approaches

### 1. Simplified Embeddings

Instead of using heavy transformer models, we'll use TF-IDF vectors which are:
- Fast to compute on CPU
- Don't require large model downloads
- Still effective for similarity search

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class SimpleEmbeddingSystem:
    def __init__(self):
        # Use character-level n-grams for better matching of short texts
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 4),
            max_features=1000
        )
        self.source_vectors = []
        self.feedback_entries = []
    
    def add_feedback(self, source, ai_translation, human_translation):
        # Store feedback entry
        entry = {
            'source': source,
            'ai_translation': ai_translation,
            'human_translation': human_translation
        }
        self.feedback_entries.append(entry)
        
        # We'll fit the vectorizer when we need to do similarity search
        # rather than updating incrementally
    
    def find_similar_corrections(self, new_source, top_k=3):
        if not self.feedback_entries:
            return []
        
        # Collect all source texts
        all_sources = [entry['source'] for entry in self.feedback_entries]
        all_sources.append(new_source)  # Include the new source for vectorization
        
        # Fit vectorizer and transform all texts
        tfidf_matrix = self.vectorizer.fit_transform(all_sources)
        
        # Calculate similarities (last row is the new source)
        similarities = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()
        
        # Get top-k most similar entries
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # Return similar corrections
        similar_corrections = []
        for idx in top_indices:
            if similarities[idx] > 0.1:  # Low threshold for character-level
                similar_corrections.append({
                    'similarity': similarities[idx],
                    'entry': self.feedback_entries[idx]
                })
        
        return similar_corrections
```

### 2. Levenshtein Distance (Already CPU-Friendly)

The Levenshtein distance implementation is already efficient for CPU:

```python
import Levenshtein

class SimpleLevenshteinAnalyzer:
    def analyze_edits(self, ai_translation, human_translation):
        # Calculate edit distance
        distance = Levenshtein.distance(ai_translation, human_translation)
        
        # Calculate similarity ratio
        ratio = Levenshtein.ratio(ai_translation, human_translation)
        
        return {
            'distance': distance,
            'similarity_ratio': ratio
        }
    
    def get_common_patterns(self, feedback_entries, threshold=0.8):
        """
        Find entries where human made significant changes
        """
        significant_changes = []
        for entry in feedback_entries:
            ai_text = entry['ai_translation']
            human_text = entry['human_translation']
            
            ratio = Levenshtein.ratio(ai_text, human_text)
            if ratio < threshold:  # Significant difference
                significant_changes.append(entry)
        
        return significant_changes
```

### 3. Simple ML Model - Linear Regression

For predicting translation quality or improvement, we'll use a simple linear regression model:

```python
from sklearn.linear_model import LinearRegression
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

class SimpleCorrectionPredictor:
    def __init__(self):
        self.model = LinearRegression()
        self.vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
        self.is_trained = False
    
    def extract_simple_features(self, source, ai_translation):
        """
        Extract simple numerical features that are fast to compute
        """
        features = []
        
        # Basic text statistics
        features.append(len(source))
        features.append(len(ai_translation))
        features.append(len(source.split()))
        features.append(len(ai_translation.split()))
        
        # Character-level features
        features.append(sum(1 for c in source if c.isupper()))
        features.append(sum(1 for c in ai_translation if c.isupper()))
        features.append(sum(1 for c in source if c.isdigit()))
        features.append(sum(1 for c in ai_translation if c.isdigit()))
        
        # Simple similarity measures
        features.append(Levenshtein.distance(source, ai_translation))
        features.append(Levenshtein.ratio(source, ai_translation))
        
        # Length ratios
        if len(source) > 0:
            features.append(len(ai_translation) / len(source))
        else:
            features.append(0)
        
        return np.array(features).reshape(1, -1)
    
    def train(self, feedback_entries):
        if len(feedback_entries) < 5:  # Need minimum data
            return False
        
        X = []
        y = []  # Target: improvement in translation quality
        
        for entry in feedback_entries:
            source = entry['source']
            ai_text = entry['ai_translation']
            human_text = entry['human_translation']
            
            # Extract features
            features = self.extract_simple_features(source, ai_text)
            X.append(features.flatten())
            
            # Target: How much better is human translation?
            # Using negative edit distance (higher is better)
            ai_distance = Levenshtein.distance(source, ai_text)
            human_distance = Levenshtein.distance(source, human_text)
            improvement = ai_distance - human_distance
            y.append(improvement)
        
        if len(X) < 5:
            return False
            
        X = np.array(X)
        y = np.array(y)
        
        # Train model
        self.model.fit(X, y)
        self.is_trained = True
        return True
    
    def predict_improvement(self, source, ai_translation):
        if not self.is_trained:
            return 0.0
        
        features = self.extract_simple_features(source, ai_translation)
        prediction = self.model.predict(features)
        return prediction[0]
```

## Simplified Integration

### Minimal Enhanced Feedback Learning System

```python
class SimpleEnhancedFeedbackLearningSystem:
    def __init__(self, db_path: str = "feedback_data.json"):
        self.db_path = db_path
        self.feedback_data = self._load_feedback()
        self.embedding_system = SimpleEmbeddingSystem()
        self.levenshtein_analyzer = SimpleLevenshteinAnalyzer()
        self.correction_predictor = SimpleCorrectionPredictor()
        self._initialize_simple_components()
    
    def _initialize_simple_components(self):
        # Initialize components with existing data
        for entry in self.feedback_data:
            self.embedding_system.add_feedback(
                entry['source'],
                entry['ai_translation'],
                entry['human_translation']
            )
        
        # Train correction predictor if we have enough data
        if len(self.feedback_data) >= 5:
            self.correction_predictor.train(self.feedback_data)
    
    def add_feedback_entry(self, source, ai_translation, human_translation,
                          source_lang, target_lang, model_info):
        # Add to base feedback system
        entry = {
            "source": source,
            "ai_translation": ai_translation,
            "human_translation": human_translation,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model_used": model_info.get('model', ''),
            "provider": model_info.get('provider', ''),
        }
        
        self.feedback_data.append(entry)
        self._save_feedback()
        
        # Update simple components
        self.embedding_system.add_feedback(source, ai_translation, human_translation)
        
        # Retrain correction predictor periodically
        if len(self.feedback_data) >= 5 and len(self.feedback_data) % 5 == 0:
            self.correction_predictor.train(self.feedback_data)
    
    def get_simple_suggestions(self, source, ai_translation):
        """
        Get simple suggestions using our lightweight approaches
        """
        suggestions = {
            'similar_corrections': [],
            'predicted_improvement': 0.0,
            'significant_changes': []
        }
        
        # Get similar corrections from simple embedding system
        similar = self.embedding_system.find_similar_corrections(source)
        suggestions['similar_corrections'] = similar
        
        # Get predicted improvement
        suggestions['predicted_improvement'] = self.correction_predictor.predict_improvement(
            source, ai_translation)
        
        # Find entries with significant changes
        significant = self.levenshtein_analyzer.get_common_patterns(
            self.feedback_data[-20:])  # Last 20 entries
        suggestions['significant_changes'] = significant
        
        return suggestions
```

## Performance Optimizations

### 1. Caching

```python
import pickle
import os

class SimpleCachingSystem:
    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def cache_model(self, model, model_name):
        """Cache trained model to disk"""
        cache_path = os.path.join(self.cache_dir, f"{model_name}.pkl")
        with open(cache_path, 'wb') as f:
            pickle.dump(model, f)
    
    def load_cached_model(self, model_name):
        """Load cached model from disk"""
        cache_path = os.path.join(self.cache_dir, f"{model_name}.pkl")
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        return None
```

### 2. Lazy Loading

Only initialize ML components when they're actually needed:

```python
class LazyEnhancedFeedbackLearningSystem:
    def __init__(self, db_path: str = "feedback_data.json"):
        self.db_path = db_path
        self.feedback_data = self._load_feedback()
        self._embedding_system = None
        self._levenshtein_analyzer = None
        self._correction_predictor = None
    
    @property
    def embedding_system(self):
        if self._embedding_system is None:
            self._embedding_system = SimpleEmbeddingSystem()
            # Initialize with existing data
            for entry in self.feedback_data:
                self._embedding_system.add_feedback(
                    entry['source'],
                    entry['ai_translation'],
                    entry['human_translation']
                )
        return self._embedding_system
    
    # Similar lazy loading for other components...
```

## Required Dependencies

For the simple implementation, you'll need these lightweight packages:

```bash
pip install scikit-learn python-Levenshtein numpy
```

These packages are:
- Well-optimized for CPU
- Don't require special hardware
- Have small memory footprints
- Are commonly available on most systems

## Benefits of Simple Approach

1. **CPU-Friendly**: All components run efficiently on CPU
2. **No GPU Required**: Works on any standard computer
3. **Fast Execution**: Simple models and algorithms execute quickly
4. **Low Memory Usage**: Minimal memory footprint
5. **Easy Deployment**: Few dependencies that are commonly available
6. **Scalable**: Can handle growing feedback data efficiently

This simple implementation provides a solid foundation that can be enhanced later if needed, while ensuring it works well for all users regardless of their hardware capabilities.