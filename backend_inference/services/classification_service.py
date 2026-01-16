from __future__ import annotations

from collections import Counter
from typing import List, Optional

import pandas as pd

from schemas.classification import (
    ClassificationPrediction,
    RequirementClassificationResponse,
)


class RequirementClassificationService:
    """Business logic wrapper around the shared classification engine."""

    def __init__(self, classifier):
        self.classifier = classifier

    def classify_texts(
        self,
        requirements: List[str],
        batch_size: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> RequirementClassificationResponse:
        if not requirements:
            raise ValueError("requirements 不能为空")

        normalized = ["" if req is None else str(req) for req in requirements]
        predictions = self.classifier.predict(normalized, batch_size=batch_size, max_length=max_length)

        items = [
            ClassificationPrediction(index=i, requirement=text, predicted_label=pred)
            for i, (text, pred) in enumerate(zip(normalized, predictions))
        ]
        distribution = Counter(predictions)

        return RequirementClassificationResponse(
            total=len(items),
            predictions=items,
            label_distribution=dict(distribution),
        )

    def classify_dataframe(
        self,
        dataframe: pd.DataFrame,
        batch_size: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> pd.DataFrame:
        if dataframe.shape[0] == 0:
            raise ValueError("CSV 没有数据行")

        df = dataframe.copy()
        texts = df.iloc[:, 0].fillna("").astype(str).tolist()
        predictions = self.classifier.predict(texts, batch_size=batch_size, max_length=max_length)

        if df.shape[1] >= 2:
            df.iloc[:, 1] = predictions
        else:
            df.insert(1, "predicted_label", predictions)
        return df
